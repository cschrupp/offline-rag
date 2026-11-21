library(ggplot2)
library(jsonlite)
root <- commandArgs(trailingOnly = TRUE)[1]
data <- fromJSON(file.path(root, "data", "observations.json"), simplifyVector = FALSE)
palette <- c("#126E82", "#EC9A29", "#8C6478")
style <- theme_minimal(base_size = 13) + theme(
  plot.title.position = "plot", plot.title = element_text(face = "bold", size = 17),
  plot.subtitle = element_text(colour = "#45586C", margin = margin(b = 13)),
  panel.grid.minor = element_blank(), legend.position = "bottom",
  plot.background = element_rect(fill = "white", colour = NA)
)
save <- function(name, plot, h = 4.5) {
  ggsave(file.path(root, "figures", paste0(name, ".png")), plot + style,
         width = 7.8, height = h, dpi = 180, bg = "white")
}
vm <- do.call(rbind, lapply(data$vm_observations, function(x) {
  backend <- switch(x$profile, "2/2" = "Torch 2/2", "2/1" = "ONNX 2/1", "4/1" = "ONNX 4/1")
  data.frame(backend, phase = x$phase, dense = x$dense_ms / 1000,
             bge = x$rerank_infer_ms / 1000, total = x$assembler_total_ms / 1000,
             cpu = x$cpu_user_s + x$cpu_system_s)
}))
base <- subset(vm, backend == "Torch 2/2")
stack <- rbind(data.frame(phase = base$phase, stage = "Dense", seconds = base$dense),
               data.frame(phase = base$phase, stage = "BGE", seconds = base$bge),
               data.frame(phase = base$phase, stage = "Other", seconds = base$total-base$dense-base$bge))
save("01-latency-breakdown", ggplot(stack, aes(phase, seconds, fill = stage)) +
       geom_col(width = .55) + scale_fill_manual(values = setNames(palette, c("BGE", "Dense", "Other"))) +
       labs(title = "BGE dominates the warm retrieval call", subtitle = "Recipes incident · 4 vCPUs · one isolated call per state",
            x = NULL, y = "Assembler wall time (s)", fill = NULL))
save("02-backend-cost", ggplot(subset(vm, phase == "warm"), aes(total, cpu, label = backend)) +
       geom_point(size = 4, colour = palette[1]) + geom_text(nudge_y = 9) +
       scale_x_continuous(limits = c(57.3, 62)) + scale_y_continuous(limits = c(100, 253)) +
       labs(title = "Four ONNX threads buy almost no wall-time gain",
            subtitle = "Recipes incident · warm assembler · one call per backend setting",
            x = "Assembler wall time (s)", y = "Assembler process CPU time (CPU-s)"))
lens <- data.frame(pair = seq_along(data$incident_lengths), tokens = unlist(data$incident_lengths))
lens$padded_width <- rep(c(368, 406), c(16, 14))
save("03-batch-padding", ggplot(lens, aes(pair)) +
       geom_col(aes(y = padded_width), fill = "#DDE7EB", width = .8) +
       geom_col(aes(y = tokens), fill = palette[1], width = .8) +
       geom_vline(xintercept = 16.5, linetype = "dashed", colour = "#60788B") +
       labs(title = "Short and long pairs share the same padding width",
            subtitle = "Original candidate order · 30 tokenized pairs · gray shows unused positions",
            x = "Fused candidate ordinal", y = "Token positions"))
arms <- c("RRF", "BGE-5", "BGE-10", "BGE-15", "BGE-20", "BGE-30")
quality <- do.call(rbind, lapply(c("ndcg5", "ndcg10", "recall10"), function(metric)
  data.frame(arm = factor(arms, levels = arms), metric,
             value = sapply(arms, function(a) data$cohorts$human_reviewed[[a]][[metric]]$mean))))
quality$metric <- factor(quality$metric, levels = c("ndcg5", "ndcg10", "recall10"),
                         labels = c("nDCG@5", "nDCG@10", "Recall@10"))
save("04-prefix-quality", ggplot(quality, aes(arm, value, colour = metric, group = metric)) +
       geom_line(linewidth = .8) + geom_point(size = 3) + scale_colour_manual(values = palette) +
       labs(title = "Fifteen candidates retain cohort-average relevance",
            subtitle = "Slice 9H-P · 16 human-reviewed queries · deterministic order replay",
            x = "RRF only or BGE input depth", y = "Macro-average score", colour = NULL))
front <- data.frame(arm = c("Hybrid RRF", "Hybrid + BGE"),
  ndcg = sapply(data[["14c_quality"]], function(x) x$ndcg_at_10),
  p50 = sapply(data[["14c_latency"]], function(x) x$stats$p50))
save("06-14c-descriptive-frontier", ggplot(front, aes(p50, ndcg, label = arm)) +
       geom_line(linetype = "dotted", colour = "#768D9C") +
       geom_point(size = 4, colour = palette[1]) + geom_text(nudge_y = .009) +
       scale_x_continuous(limits = c(5, 8.1)) + scale_y_continuous(limits = c(.77, .865)) +
       labs(title = "Two observed points on the Slice 14C frontier",
            subtitle = "22 development queries · 220 warm observations per arm",
            x = "Median total wall time (s)", y = "Macro nDCG@10"))
raw <- lapply(readLines(file.path(root, "data", "batch-pilot.jsonl")), fromJSON, simplifyVector = FALSE)
trials <- Filter(function(r) !is.null(r$arm) && !isTRUE(r$warmup), raw)
if (length(trials) == 4) {
  trial <- do.call(rbind, lapply(trials, function(r) data.frame(
    arm = r$arm, block = factor(r$block), wall = sum(sapply(r$batches, function(b) b[[2]]))
  )))
  save("05-local-forward-pilot", ggplot(trial, aes(arm, wall, group = block, colour = block)) +
    geom_line(linewidth = .8) + geom_point(size = 4) + scale_colour_manual(values = palette) +
    labs(title = "Forward time under two batching strategies",
         subtitle = "Local CPU · one synthetic length-matched workload · AB and BA blocks",
         x = NULL, y = "Forward wall time (s)", colour = "Measured block"))
}

human <- Filter(function(row) row$cohort == "human_reviewed", data$cases)
paired <- do.call(rbind, lapply(human, function(row) data.frame(
  label = paste(row$ordinal, row$category, sep = " · "),
  change = row$arms[["BGE-15"]]$ndcg10 - row$arms[["BGE-30"]]$ndcg10
)))
paired$label <- factor(paired$label, levels = rev(paired$label))
paired$outcome <- ifelse(paired$change < 0, "Regression",
                         ifelse(paired$change > 0, "Improvement", "Tie"))
save("07-per-query-depth-changes",
     ggplot(paired, aes(change, label, colour = outcome)) +
       geom_vline(xintercept = 0, colour = "#B2C0C9") +
       geom_segment(aes(x = 0, xend = change, yend = label), linewidth = .7) +
       geom_point(size = 2.6) +
       scale_colour_manual(values = c(Regression = "#B54A32", Improvement = "#126E82", Tie = "#596E7B")) +
       labs(title = "Similar averages hide two query-level regressions",
            subtitle = "Slice 9H-P · 16 human-reviewed queries · paired replay",
            x = "nDCG@10 change (BGE-15 minus BGE-30)", y = NULL, colour = NULL), h = 6.5)
