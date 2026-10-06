import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";

type Variant = "primary" | "secondary" | "danger";

function variantClass(variant: Variant, className = ""): string {
  return `btn btn-${variant} ${className}`.trim();
}

type NativeButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  children: ReactNode;
};

type LinkAsButtonProps = {
  variant?: Variant;
  children: ReactNode;
  to: string;
  className?: string;
};

export function Button(props: NativeButtonProps | LinkAsButtonProps) {
  if ("to" in props) {
    const { to, variant = "primary", className = "", children } = props;
    return (
      <Link to={to} className={variantClass(variant, className)}>
        {children}
      </Link>
    );
  }

  const buttonProps = props as NativeButtonProps;
  const {
    variant = "primary",
    className = "",
    children,
    type = "button",
    ...rest
  } = buttonProps;

  return (
    <button
      type={type}
      className={variantClass(variant, className)}
      {...rest}
    >
      {children}
    </button>
  );
}
