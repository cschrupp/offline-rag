import type { ReactNode } from "react";

type Tone = "ready" | "busy" | "empty" | "error";

type Props = {
  tone: Tone;
  label: string;
  icon?: ReactNode;
};

export function Badge({ tone, label, icon }: Props) {
  return (
    <span className={`badge badge-${tone}`}>
      {icon}
      <span>{label}</span>
    </span>
  );
}
