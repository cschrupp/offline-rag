import { useSearchParams } from "react-router-dom";
import { Button } from "../../../components/Button";
import { QuestionCheckPreviewSession } from "./QuestionCheckPreviewSession";
import { RapidFirePreviewSession } from "./RapidFirePreviewSession";

export type PresentationReviewTarget = "question_check" | "rapid_fire";

type Props = {
  campaignId: string;
};

function parseTarget(raw: string | null): PresentationReviewTarget {
  return raw === "rapid_fire" ? "rapid_fire" : "question_check";
}

export function PresentationReviewWorkspace({ campaignId }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const target = parseTarget(searchParams.get("presentation"));

  function selectTarget(next: PresentationReviewTarget) {
    const params = new URLSearchParams(searchParams);
    params.set("presentation", next);
    setSearchParams(params, { replace: true });
  }

  return (
    <div className="stack" data-testid="presentation-review-workspace">
      <p className="muted" role="status" data-testid="presentation-review-banner">
        Preview only — responses here do not change Gold.
      </p>

      <div
        className="row"
        role="tablist"
        aria-label="Presentation review targets"
        style={{ flexWrap: "wrap" }}
      >
        <Button
          variant={target === "question_check" ? "primary" : "secondary"}
          aria-selected={target === "question_check"}
          onClick={() => selectTarget("question_check")}
        >
          Question Check
        </Button>
        <Button
          variant={target === "rapid_fire" ? "primary" : "secondary"}
          aria-selected={target === "rapid_fire"}
          onClick={() => selectTarget("rapid_fire")}
        >
          Rapid Fire
        </Button>
      </div>

      {target === "question_check" ? (
        <QuestionCheckPreviewSession campaignId={campaignId} />
      ) : (
        <RapidFirePreviewSession campaignId={campaignId} />
      )}
    </div>
  );
}
