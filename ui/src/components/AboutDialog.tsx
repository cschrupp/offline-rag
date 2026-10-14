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
