import { useApiClient } from "@neospacetech/neosuite-runtime/react";
import { radii, spacing } from "@neospacetech/neosuite-tokens";
import { Button, Row, Stack, Text, useTheme } from "@neospacetech/neosuite-ui";
import { useCallback, useEffect, useState } from "react";
import { ScrollView, View } from "react-native";
import { errorMessage, getThread, updateMessage } from "../api";
import { fullDate } from "../format";
import type { Mailbox, Message, Thread } from "../types";

export interface ThreadViewProps {
  threadId: string;
  mailboxes: readonly Mailbox[];
  onReply: (message: Message) => void;
  /** Called after the thread changed (read state, flags, mailboxes). */
  onChanged: () => void;
  /** Reload trigger from the screen. */
  revision: number;
}

function MessageCard({ message }: { message: Message }) {
  const { colors } = useTheme();
  const recipients = [...message.to, ...message.cc].map((a) => a.name ?? a.email).join(", ");
  return (
    <View
      role="article"
      accessibilityLabel={`From ${message.from.name ?? message.from.email}, ${fullDate(message.received_at)}`}
      style={{ padding: spacing.lg, gap: spacing.sm, borderRadius: radii.lg, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceRaised }}
    >
      <Row gap="sm" justify="space-between" wrap>
        <Text variant="bodyStrong" selectable style={{ flexShrink: 1 }}>
          {message.from.display}
        </Text>
        <Text variant="caption" tone="muted">
          {fullDate(message.received_at)}
        </Text>
      </Row>
      {recipients ? (
        <Text variant="caption" tone="muted" selectable>
          {`To ${recipients}`}
        </Text>
      ) : null}
      <Text selectable>{message.text || "(no text)"}</Text>
      {message.attachments.length > 0 ? (
        <Text variant="caption" tone="muted">{`Attachments: ${message.attachments.join(", ")}`}</Text>
      ) : null}
    </View>
  );
}

/** A conversation, oldest message first, with reply, read, flag and archive actions. */
export function ThreadView({ threadId, mailboxes, onReply, onChanged, revision }: ThreadViewProps) {
  const client = useApiClient();
  const [thread, setThread] = useState<Thread | null>(null);
  const [error, setError] = useState<string | undefined>();
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getThread(client, threadId, controller.signal)
      .then(async (loaded) => {
        setThread(loaded);
        setError(undefined);
        const unread = loaded.messages.filter((m) => !m.seen);
        if (unread.length > 0) {
          await Promise.all(unread.map((m) => updateMessage(client, m.id, { seen: true }, controller.signal)));
          onChanged();
        }
      })
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setError(errorMessage(e));
      });
    return () => controller.abort();
  }, [client, threadId, revision, onChanged]);

  const act = useCallback(
    async (name: string, change: (messages: Message[]) => Promise<unknown>) => {
      if (!thread) return;
      setBusy(name);
      setError(undefined);
      try {
        await change(thread.messages);
        onChanged();
      } catch (e) {
        setError(errorMessage(e));
      } finally {
        setBusy(null);
      }
    },
    [onChanged, thread],
  );

  if (!thread) {
    return (
      <Text tone={error ? "danger" : "muted"} role={error ? "alert" : undefined} style={{ padding: spacing.lg }}>
        {error ?? "Loading…"}
      </Text>
    );
  }

  const last = thread.messages[thread.messages.length - 1];
  const archive = mailboxes.find((m) => m.role === "archive" && m.owner === thread.owner);
  const flagged = thread.messages.some((m) => m.flagged);

  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.lg }}>
      <Text variant="title" headingLevel={2} selectable>
        {thread.subject || "(no subject)"}
      </Text>
      <Row gap="sm" wrap>
        {last ? <Button label="Reply" onPress={() => onReply(last)} /> : null}
        <Button
          label="Mark unread"
          variant="secondary"
          loading={busy === "unread"}
          onPress={() => act("unread", (messages) => (last ? updateMessage(client, last.id, { seen: false }) : Promise.resolve(messages)))}
        />
        <Button
          label={flagged ? "Unflag" : "Flag"}
          variant="secondary"
          loading={busy === "flag"}
          onPress={() => act("flag", (messages) => Promise.all(messages.map((m) => updateMessage(client, m.id, { flagged: !flagged }))))}
        />
        {archive ? (
          <Button
            label="Archive"
            variant="secondary"
            loading={busy === "archive"}
            onPress={() => act("archive", (messages) => Promise.all(messages.map((m) => updateMessage(client, m.id, { mailbox_ids: [archive.id] }))))}
          />
        ) : null}
      </Row>
      {error ? (
        <Text tone="danger" role="alert">
          {error}
        </Text>
      ) : null}
      <Stack gap="md">
        {thread.messages.map((message) => (
          <MessageCard key={message.id} message={message} />
        ))}
      </Stack>
    </ScrollView>
  );
}
