library(ggplot2)
input <- read.csv(commandArgs(TRUE)[1])
input$phase <- factor(input$phase, levels = c("warm", "cold"))
input$stage <- factor(input$stage, levels = unique(input$stage))
plot <- ggplot(input, aes(fill = stage)) +
  geom_rect(aes(xmin = start_s, xmax = end_s,
                ymin = as.numeric(phase) - .26, ymax = as.numeric(phase) + .26),
            inherit.aes = TRUE) +
  scale_y_continuous(breaks = c(1, 2), labels = c("Warm", "Cold")) +
  scale_fill_manual(values = c("#307093", "#85A9BC", "#ADC7CD", "#E5B467",
                               "#D8703B", "#A58CA8", "#69896E", "#CBD5DF")) +
  labs(title = "Where Rich's workspace spent its retrieval time",
       subtitle = "One cold and one warm call · Same snapshot and process · Original question",
       x = "Cumulative assembler wall time (seconds)", y = NULL, fill = NULL) +
  theme_minimal(base_size = 13) +
  theme(plot.title.position = "plot", plot.title = element_text(face = "bold"),
        legend.position = "bottom", panel.grid.minor = element_blank())
ggsave(commandArgs(TRUE)[2], plot = plot, width = 8.6, height = 3.6, dpi = 180, bg = "white")
