import type { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

type FieldProps = {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
};

export function Field({ id, label, hint, error, children }: FieldProps) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      {hint ? (
        <p id={hintId} className="muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="error-box" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  error?: string;
};

export function TextInput({
  id,
  label,
  hint,
  error,
  ...rest
}: InputProps & { id: string }) {
  const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-error` : null]
    .filter(Boolean)
    .join(" ");
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      <input id={id} aria-describedby={describedBy || undefined} {...rest} />
    </Field>
  );
}

type TextAreaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label: string;
  hint?: string;
  error?: string;
};

export function TextArea({
  id,
  label,
  hint,
  error,
  ...rest
}: TextAreaProps & { id: string }) {
  const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-error` : null]
    .filter(Boolean)
    .join(" ");
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      <textarea id={id} aria-describedby={describedBy || undefined} {...rest} />
    </Field>
  );
}
