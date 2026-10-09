import { useApiClient } from "@neospacetech/neosuite-runtime/react";
import { paneWidths, spacing } from "@neospacetech/neosuite-tokens";
import { AdaptivePanel, Button, ListDetail, Row, Stack, Text, useBreakpoint, useTheme } from "@neospacetech/neosuite-ui";
import { useCallback, useEffect, useState } from "react";
import { FlatList, View } from "react-native";
import { errorMessage, listMailboxes, listThreads, streamChanges } from "../api";
import { MailboxList } from "../components/MailboxList";
import { ThreadRow } from "../components/ThreadRow";
import { mailboxLabel, replySubject } from "../format";
import type { Mailbox, Message, ThreadSummary } from "../types";
import { Composer, type ComposerInitial } from "./Composer";
import { ThreadView } from "./ThreadView";

interface ComposeState {
  owner: string;
  initial: ComposerInitial;
}

/**
 * Three-pane mail: mailboxes, conversations and the open conversation.
 *
 * Layout by breakpoint: from expanded up the mailboxes are a sidebar beside the list and the
 * conversation; on medium the mailboxes become chips above a side-by-side list and conversation;
 * on compact the list and the conversation stack, with a back button. The composer is a sheet on
 * compact and a side panel wider. Selection and drafts live here, so resizing never loses them.
 */
export function MailScreen() {
  const client = useApiClient();
  const { colors } = useTheme();
  const { breakpoint, width } = useBreakpoint();
  const sidebar = breakpoint === "expanded" || breakpoint === "large" || breakpoint === "tv";

  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [mailboxId, setMailboxId] = useState<string | null>(null);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [compose, setCompose] = useState<ComposeState | null>(null);
  const [error, setError] = useState<string | undefined>();
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision((r) => r + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const boxes = await listMailboxes(client, controller.signal);
        setMailboxes(boxes);
        const current = mailboxId && boxes.some((b) => b.id === mailboxId) ? mailboxId : (boxes.find((b) => b.role === "inbox") ?? boxes[0])?.id ?? null;
        if (current !== mailboxId) setMailboxId(current);
        setThreads(current ? await listThreads(client, current, controller.signal) : []);
        setError(undefined);
      } catch (e) {
        if (!controller.signal.aborted) setError(errorMessage(e));
      }
    })();
    return () => controller.abort();
  }, [client, mailboxId, revision]);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    (async () => {
      try {
        for await (const _change of streamChanges(client, 0, controller.signal)) {
          clearTimeout(timer);
          timer = setTimeout(reload, 300);
        }
      } catch {
        // Live updates are a convenience; the screen still works without them.
      }
    })();
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [client, reload]);

  const mailbox = mailboxes.find((m) => m.id === mailboxId);
  const owner = mailbox?.owner ?? mailboxes[0]?.owner;

  const selectMailbox = useCallback((id: string) => {
    setMailboxId(id);
    setThreadId(null);
  }, []);

  const startCompose = useCallback(
    (replyTo?: Message) => {
      const who = replyTo?.owner ?? owner;
      if (!who) return;
      setCompose({
        owner: who,
        initial: replyTo
          ? {
              sender: replyTo.to[0]?.display ?? "",
              to: replyTo.from.display,
              cc: "",
              subject: replySubject(replyTo.subject),
              text: "",
              replyToId: replyTo.id,
            }
          : { sender: "", to: "", cc: "", subject: "", text: "" },
      });
    },
    [owner],
  );

  const list = (
    <FlatList
      data={threads}
      keyExtractor={(t) => t.id}
      accessibilityLabel={mailbox ? `Conversations in ${mailboxLabel(mailbox)}` : "Conversations"}
      ListEmptyComponent={
        <Text tone="muted" style={{ padding: spacing.lg }}>
          {mailboxes.length === 0 ? "No mailboxes yet." : "No conversations here."}
        </Text>
      }
      renderItem={({ item }) => <ThreadRow thread={item} selected={item.id === threadId} onPress={(t) => setThreadId(t.id)} />}
    />
  );

  const panes = (
    <ListDetail
      selectedId={threadId}
      onSelectionChange={setThreadId}
      backLabel={mailbox ? mailboxLabel(mailbox) : "Back"}
      renderList={() => list}
      renderDetail={({ selectedId }) => (
        <ThreadView threadId={selectedId} mailboxes={mailboxes} onReply={startCompose} onChanged={reload} revision={revision} />
      )}
      emptyDetail={
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.lg }}>
          <Text tone="muted">Select a conversation to read it.</Text>
        </View>
      }
    />
  );

  const header = (
    <Row gap="sm" justify="space-between" wrap padding="md" style={{ borderBottomWidth: 1, borderColor: colors.border }}>
      <Text variant="subtitle" headingLevel={1} style={{ flexShrink: 1 }}>
        {mailbox ? mailboxLabel(mailbox) : "Mail"}
      </Text>
      <Button label="Compose" onPress={() => startCompose()} disabled={!owner} />
    </Row>
  );

  const body = sidebar ? (
    <View style={{ flex: 1, flexDirection: "row", minWidth: 0 }}>
      <View style={{ width: Math.min(paneWidths.sidebar, Math.floor(width * 0.2)), borderRightWidth: 1, borderColor: colors.border }}>
        <View style={{ padding: spacing.md }}>
          <Button label="Compose" onPress={() => startCompose()} disabled={!owner} fullWidth />
        </View>
        <MailboxList mailboxes={mailboxes} selectedId={mailboxId} onSelect={selectMailbox} layout="column" />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>{panes}</View>
    </View>
  ) : (
    <Stack flex>
      {header}
      {threadId === null || breakpoint !== "compact" ? (
        <MailboxList mailboxes={mailboxes} selectedId={mailboxId} onSelect={selectMailbox} layout="row" />
      ) : null}
      <View style={{ flex: 1, minHeight: 0 }}>{panes}</View>
    </Stack>
  );

  return (
    <AdaptivePanel
      open={compose !== null}
      onClose={() => setCompose(null)}
      title={compose?.initial.replyToId ? "Reply" : "New message"}
      panel={
        compose ? (
          <Composer
            key={compose.initial.replyToId ?? "new"}
            owner={compose.owner}
            initial={compose.initial}
            onSent={() => {
              setCompose(null);
              reload();
            }}
            onCancel={() => setCompose(null)}
          />
        ) : null
      }
    >
      <Stack flex>
        {error ? (
          <Text tone="danger" role="alert" style={{ padding: spacing.md }}>
            {error}
          </Text>
        ) : null}
        {body}
      </Stack>
    </AdaptivePanel>
  );
}
