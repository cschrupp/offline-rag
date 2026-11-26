import { useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import { useNavigate } from "react-router-dom";
import { Button } from "./Button";
import { ModalDialog } from "./ModalDialog";
import {
  AUTHOR_NAME,
  CONTACT_EMAIL,
  CONTACT_MAILTO,
  PRODUCT_DESCRIPTOR,
  PRODUCT_NAME,
  PRODUCT_VERSION,
  REPOSITORY_URL,
} from "../product/identity";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function AboutDialog({ open, onClose }: Props) {
  const navigate = useNavigate();
  const [runtimeRevision, setRuntimeRevision] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    void apiRequest<{ source_sha: string | null }>("/v1/runtime/revision", {
      signal: controller.signal,
    }).then(
      (result) => { if (!controller.signal.aborted) setRuntimeRevision(result?.source_sha ?? null); },
      () => { if (!controller.signal.aborted) setRuntimeRevision(null); },
    );
    return () => controller.abort();
  }, [open]);

  return (
    <ModalDialog
      open={open}
      title={`About ${PRODUCT_NAME}`}
      onClose={onClose}
    >
      <div className="about-dialog-body">
        <p className="about-product-name">{PRODUCT_NAME}</p>
        <p className="about-product-descriptor">{PRODUCT_DESCRIPTOR}</p>
        <p className="muted">Version {PRODUCT_VERSION}</p>
        <p className="muted">Backend revision <code>{runtimeRevision ?? "Unavailable"}</code></p>
        <p className="muted">Frontend revision <code>{import.meta.env.VITE_SENECA_SOURCE_SHA || "Unavailable"}</code></p>
        <p>
          Local-first, evidence-grounded workspace for private technical
          knowledge.
        </p>
        <p>
          Created by {AUTHOR_NAME}
          <br />
          <a href={CONTACT_MAILTO}>{CONTACT_EMAIL}</a>
        </p>
        <p className="about-pillars">
          Local-first · Evidence-grounded · Private by design
        </p>
        <p className="muted">© 2026 {AUTHOR_NAME}</p>
        <div className="about-actions">
          <a className="btn btn-secondary" href={CONTACT_MAILTO}>
            Contact
          </a>
          <Button
            variant="secondary"
            onClick={() => {
              onClose();
              navigate("/welcome");
            }}
          >
            Show welcome screen
          </Button>
          <a
            className="btn btn-secondary"
            href={REPOSITORY_URL}
            target="_blank"
            rel="noreferrer noopener"
          >
            Source repository
          </a>
          <Button variant="primary" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </ModalDialog>
  );
}
