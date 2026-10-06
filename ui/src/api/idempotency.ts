/** One opaque key represents one user intent (S16-D14). */
export function createIdempotencyKey(): string {
  return crypto.randomUUID();
}

/**
 * Holds the idempotency key for a single user intent across transport retries.
 * Create a new IntentHandle for a materially new user action.
 */
export class IntentHandle {
  readonly key: string;

  constructor(key: string = createIdempotencyKey()) {
    this.key = key;
  }

  /** Explicit retry after a terminal backend failure is a new intent. */
  static newIntent(): IntentHandle {
    return new IntentHandle();
  }
}
