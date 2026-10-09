import { useApiClient } from "@neospacetech/neosuite-runtime/react";
import { Stack, Text } from "@neospacetech/neosuite-ui";
import { useEffect, useState } from "react";
import { errorMessage, listMailboxes, listThreads } from "../api";
import { ThreadRow } from "../components/ThreadRow";
import type { ThreadSummary } from "../types";

export interface InboxWidgetProps {
  /** Most conversations to show. Defaults to 5. */
  limit?: number;
  onOpen?: (thread: ThreadSummary) => void;
}

/** Unread count and the latest conversations in the inbox. Embeddable in other products and NeoMind. */
export function InboxWidget({ limit = 5, onOpen }: InboxWidgetProps) {
  const client = useApiClient();
  const [state, setState] = useState<{ unread: number; threads: ThreadSummary[] } | null>(null);
  const [error, setError] = useState<string | undefined>();

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const inbox = (await listMailboxes(client, controller.signal)).find((m) => m.role === "inbox");
        const threads = inbox ? await listThreads(client, inbox.id, controller.signal) : [];
        setState({ unread: inbox?.unread ?? 0, threads: threads.slice(0, limit) });
      } catch (e) {
        if (!controller.signal.aborted) setError(errorMessage(e));
      }
    })();
    return () => controller.abort();
  }, [client, limit]);

  if (error) return <Text tone="danger">{error}</Text>;
  if (!state) return <Text tone="muted">Loading…</Text>;
  return (
    <Stack gap="xs" accessibilityLabel="Inbox">
      <Text variant="label">{state.unread > 0 ? `${state.unread} unread` : "All caught up"}</Text>
      {state.threads.map((thread) => (
        <ThreadRow key={thread.id} thread={thread} onPress={onOpen} />
      ))}
    </Stack>
  );
}
