library(ggplot2)
args <- commandArgs(trailingOnly = TRUE)
results <- read.csv(args[1])
results$comparison <- factor(results$comparison, levels = c("BA", "CA", "DA", "DB", "DC"),
                             labels = c("B vs A", "C vs A", "D vs A", "D vs B", "D vs C"))
results$endpoint <- factor(results$endpoint,
  levels = c("forward_s", "assembler_s", "assembler_cpu_s"),
  labels = c("BGE forward wall", "Assembler wall", "Assembler CPU"))
plot <- ggplot(results, aes(x = comparison, y = reduction_pct)) +
  geom_hline(yintercept = 0, colour = "#A0AEB8") +
  geom_point(aes(colour = factor(block)), position = position_dodge(width = .40), size = 2.7) +
  stat_summary(fun = median, geom = "point", shape = 95, size = 12, colour = "#243848") +
  facet_wrap(~ endpoint) +
  scale_colour_manual(values = c("#126E82", "#5650A0", "#B5641C", "#377A54")) +
  labs(title = "Depth and batching on the same Recipes retrieval workload",
       subtitle = "Four matched blocks · Four-vCPU VM · Positive values favor the first arm",
       x = "Within-block comparison", y = "Reduction relative to reference (%)",
       colour = "Block",
       caption = "A = 30 consecutive. B = 15 consecutive. C = 30 sorted-eight. D = 15 sorted-eight.") +
  theme_minimal(base_size = 12) +
  theme(legend.position = "bottom", panel.grid.minor = element_blank(),
        axis.text.x = element_text(angle = 22, hjust = 1),
        plot.title = element_text(face = "bold"), plot.title.position = "plot")
ggsave(args[2], plot = plot, width = 10.2, height = 4.4, dpi = 180, bg = "white")
