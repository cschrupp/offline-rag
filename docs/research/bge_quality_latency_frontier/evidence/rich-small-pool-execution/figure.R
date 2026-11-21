library(ggplot2)
args <- commandArgs(trailingOnly = TRUE)
results <- read.csv(args[1])
results$arm <- factor(results$arm, levels = c("B", "C", "D"),
                      labels = c("5 + 5", "4 + 4 + 2", "2 + 2 + 2 + 2 + 2"))
results$endpoint <- factor(results$endpoint,
  levels = c("forward_s", "assembler_s", "assembler_cpu_s"),
  labels = c("BGE forward wall", "Assembler wall", "Assembler CPU"))
threshold <- data.frame(endpoint = levels(results$endpoint), gate = c(20, 20, -5))
plot <- ggplot(results, aes(x = arm, y = reduction_pct)) +
  geom_hline(yintercept = 0, colour = "#A0AEB8") +
  geom_hline(data = threshold, aes(yintercept = gate), linetype = "dashed", colour = "#B75B36") +
  geom_point(aes(colour = factor(block)), position = position_dodge(width = .40), size = 2.7) +
  stat_summary(fun = median, geom = "point", shape = 95, size = 12, colour = "#243848") +
  facet_wrap(~ endpoint) +
  scale_colour_manual(values = c("#126E82", "#5650A0", "#B5641C", "#377A54")) +
  labs(title = "Smaller batches on the same ten Rich workspace candidates",
       subtitle = "Four matched blocks · Four-vCPU VM · Positive values favor the treatment",
       x = "Consecutive batch grouping", y = "Reduction versus the original batch (%)",
       colour = "Block",
       caption = "Dark marks show paired medians. Dashed lines show the wall and CPU gates.") +
  theme_minimal(base_size = 12) +
  theme(legend.position = "bottom", panel.grid.minor = element_blank(),
        axis.text.x = element_text(angle = 22, hjust = 1),
        plot.title = element_text(face = "bold"), plot.title.position = "plot")
ggsave(args[2], plot = plot, width = 10.2, height = 4.4, dpi = 180, bg = "white")
