import { useState } from "react";

export const FROG_ASSETS = {
  logo: "/mascots/frog-logo.png",
  writing: "/mascots/frog-writing.png",
  peeking: "/mascots/frog-peeking.png",
  sleeping: "/mascots/frog-sleeping.png",
  encouraging: "/mascots/frog-encouraging.png",
  pointing: "/mascots/frog-pointing.png",
  lilypad: "/mascots/frog-lilypad-smile.png",
} as const;

export type FrogVariant = keyof typeof FROG_ASSETS;
type Props = { variant: FrogVariant; className?: string; alt?: string };

export default function FrogMascot({ variant, className = "", alt = "" }: Props) {
  const [failedPath, setFailedPath] = useState<string | null>(null);
  const src = FROG_ASSETS[variant];
  const classes = `frog-mascot select-none pointer-events-none object-contain ${className}`;
  if (!src || failedPath === src) {
    return <span className={`${classes} mascot-placeholder`} role={alt ? "img" : undefined}
      aria-label={alt || undefined} aria-hidden={alt ? undefined : true} data-mascot-placeholder={variant}>FW</span>;
  }
  return <img src={src} alt={alt} className={classes} draggable={false}
    data-mascot={variant} onError={() => setFailedPath(src)} />;
}
