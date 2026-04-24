import clsx, { type ClassValue } from "clsx";

/** Thin Tailwind class-merge helper. Not using tailwind-merge to keep deps lean;
 * we rarely pass conflicting utilities and can prune manually if needed. */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}
