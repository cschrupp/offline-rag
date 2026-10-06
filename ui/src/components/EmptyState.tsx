import type { ReactNode } from "react";
import { Card } from "./Card";

type Props = {
  title: string;
  body: string;
  action?: ReactNode;
};

export function EmptyState({ title, body, action }: Props) {
  return (
    <Card>
      <h2>{title}</h2>
      <p className="muted">{body}</p>
      {action ? <div className="row">{action}</div> : null}
    </Card>
  );
}
