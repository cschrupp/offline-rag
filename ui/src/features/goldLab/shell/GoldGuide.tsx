import { useState } from "react";
import { Button } from "../../../components/Button";
import type { ExpertCampaignState } from "./deriveExpertCampaignState";
import {
  isGoldGuideDismissed,
  setGoldGuideDismissed,
} from "./goldGuideStorage";

type Props = {
  state: ExpertCampaignState;
};

export function GoldGuide({ state }: Props) {
  const [open, setOpen] = useState(() => !isGoldGuideDismissed());

  function dismiss() {
    setGoldGuideDismissed(true);
    setOpen(false);
  }

  function reopen() {
    setGoldGuideDismissed(false);
    setOpen(true);
  }

  if (!open) {
    return (
      <div className="gold-lab-guide-collapsed">
        <Button variant="secondary" onClick={reopen}>
          Show Gold Guide
        </Button>
      </div>
    );
  }

  const step =
    state.qcPending > 0
      ? 1
      : state.relevancePending > 0
        ? 2
        : 3;

  return (
    <section
      className="card gold-lab-guide"
      data-testid="gold-guide"
      aria-labelledby="gold-guide-heading"
    >
      <div className="row gold-lab-card-header">
        <h2 id="gold-guide-heading" style={{ margin: 0 }}>
          Gold Guide
        </h2>
        <Button
          variant="secondary"
          onClick={dismiss}
          aria-label="Dismiss Gold Guide for this browser session"
        >
          Dismiss
        </Button>
      </div>
      <ol className="gold-lab-guide-steps">
        <li aria-current={step === 1 ? "step" : undefined}>
          Review proposed questions.
        </li>
        <li aria-current={step === 2 ? "step" : undefined}>
          Accepted or edited questions unlock evidence judgment.
        </li>
        <li aria-current={step === 3 ? "step" : undefined}>
          Judge evidence until no primary Gold work remains.
        </li>
      </ol>
      <p className="muted" style={{ margin: 0 }}>
        Current step:{" "}
        {step === 1
          ? "Review questions"
          : step === 2
            ? "Judge evidence"
            : "Canonical Gold work complete"}
      </p>
    </section>
  );
}
