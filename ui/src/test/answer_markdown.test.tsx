import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { AnswerMarkdown } from "../components/AnswerMarkdown";

it("renders answer headings, emphasis, lists, tables and code", () => {
  const { container } = render(<AnswerMarkdown text={[
    "## Cue Recognition", "", "1. **Notice** the cue.", "2. *Compare* patterns.", "",
    "- first", "- second", "", "| Cue | Example |", "| --- | --- |", "| Light | A signal |", "",
    "```text", "let value = 1", "```",
  ].join("\n")} />);
  expect(screen.getByRole("heading", { name: "Cue Recognition" })).toBeVisible();
  expect(container.querySelector("strong")).toHaveTextContent("Notice");
  expect(container.querySelector("em")).toHaveTextContent("Compare");
  expect(container.querySelectorAll("ol li")).toHaveLength(2);
  expect(container.querySelectorAll("ul li")).toHaveLength(2);
  expect(screen.getByRole("cell", { name: "A signal" })).toBeVisible();
  expect(container.querySelector("pre code")).toHaveTextContent("let value = 1");
});

it("leaves HTML and URL markup inert and preserves the citation control", () => {
  const { container } = render(<AnswerMarkdown
    text={'<script>example</script>\n[Link](javascript:example)\n\n**Claim**'}
    suffix={<button type="button">Citation 1</button>}
  />);
  expect(container.querySelector("script, a, img")).toBeNull();
  expect(screen.getByText(/<script>example<\/script>/)).toBeVisible();
  expect(screen.getByRole("button", { name: "Citation 1" })).toBeVisible();
});
