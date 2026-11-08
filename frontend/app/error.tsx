"use client";

// Shown only when no good page has been generated yet; once one exists, a failed
// revalidation keeps serving it instead.
export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <main>
      <h1>EV board</h1>
      <p className="empty">The board is not available right now. Try again in a minute.</p>
      <button type="button" onClick={reset}>
        Retry
      </button>
    </main>
  );
}
