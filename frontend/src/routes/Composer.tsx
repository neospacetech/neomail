import { useApiClient } from "@neospacetech/neosuite-runtime/react";
import { spacing } from "@neospacetech/neosuite-tokens";
import { Button, Stack, Text, TextField, useBreakpoint } from "@neospacetech/neosuite-ui";
import { useCallback, useState } from "react";
import { ScrollView, View } from "react-native";
import { checkSmartSend, errorMessage, isSmartSendBlock, sendMessage } from "../api";
import { FindingList } from "../components/FindingList";
import { splitRecipients } from "../format";
import type { Draft, SmartSendFinding } from "../types";

export interface ComposerInitial {
  sender: string;
  to: string;
  cc: string;
  subject: string;
  text: string;
  replyToId?: string;
}

export interface ComposerProps {
  /** Principal sending, whose calendar Smart Send checks against. */
  owner: string;
  initial: ComposerInitial;
  onSent: () => void;
  onCancel: () => void;
}

/**
 * Write and send a message. Smart Send checks the draft on demand and again on Send; a conflict
 * stops the send and offers "Send anyway", while warnings never block.
 */
export function Composer({ owner, initial, onSent, onCancel }: ComposerProps) {
  const client = useApiClient();
  const { breakpoint } = useBreakpoint();
  const compact = breakpoint === "compact";
  const [form, setForm] = useState(initial);
  const [attachments, setAttachments] = useState<string[]>([]);
  const [attachmentName, setAttachmentName] = useState("");
  const [findings, setFindings] = useState<SmartSendFinding[] | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [busy, setBusy] = useState<"check" | "send" | null>(null);

  const set = useCallback(<K extends keyof ComposerInitial>(key: K, value: ComposerInitial[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
    setFindings(null);
    setBlocked(false);
  }, []);

  const draft = useCallback(
    (sendAnyway = false): Draft => ({
      owner,
      sender: form.sender,
      to: splitRecipients(form.to),
      cc: splitRecipients(form.cc),
      bcc: [],
      subject: form.subject,
      text: form.text,
      attachments,
      reply_to_id: form.replyToId ?? null,
      send_anyway: sendAnyway,
    }),
    [attachments, form, owner],
  );

  const check = useCallback(async () => {
    setBusy("check");
    setError(undefined);
    try {
      const report = await checkSmartSend(client, draft());
      setFindings(report.findings);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }, [client, draft]);

  const send = useCallback(
    async (sendAnyway: boolean) => {
      setBusy("send");
      setError(undefined);
      try {
        await sendMessage(client, draft(sendAnyway));
        onSent();
      } catch (e) {
        if (isSmartSendBlock(e)) {
          setBlocked(true);
          try {
            setFindings((await checkSmartSend(client, draft())).findings);
          } catch {
            // The block message below still explains what happened.
          }
        }
        setError(errorMessage(e));
      } finally {
        setBusy(null);
      }
    },
    [client, draft, onSent],
  );

  const addAttachment = () => {
    const name = attachmentName.trim();
    if (!name) return;
    setAttachments((current) => [...current, name]);
    setAttachmentName("");
    setFindings(null);
  };

  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }} keyboardShouldPersistTaps="handled">
      <TextField label="From" value={form.sender} onChangeText={(v) => set("sender", v)} autoComplete="email" inputMode="email" required />
      <TextField label="To" value={form.to} onChangeText={(v) => set("to", v)} helperText="Separate addresses with commas." inputMode="email" required />
      <TextField label="Cc" value={form.cc} onChangeText={(v) => set("cc", v)} inputMode="email" />
      <TextField label="Subject" value={form.subject} onChangeText={(v) => set("subject", v)} />
      <TextField label="Message" value={form.text} onChangeText={(v) => set("text", v)} multiline numberOfLines={10} style={{ minHeight: 200 }} />
      <Stack gap="xs">
        <View style={{ flexDirection: compact ? "column" : "row", gap: spacing.sm, alignItems: compact ? "stretch" : "flex-end" }}>
          <TextField label="Attachment" value={attachmentName} onChangeText={setAttachmentName} onSubmitEditing={addAttachment} style={compact ? undefined : { flex: 1 }} />
          <Button label="Attach" variant="secondary" onPress={addAttachment} fullWidth={compact} />
        </View>
        {attachments.length > 0 ? <Text tone="muted">{`Attached: ${attachments.join(", ")}`}</Text> : null}
      </Stack>

      {findings ? (findings.length > 0 ? <FindingList findings={findings} /> : <Text tone="success">Smart Send found nothing to check.</Text>) : null}
      {error ? (
        <Text tone="danger" role="alert">
          {error}
        </Text>
      ) : null}

      <View style={{ flexDirection: compact ? "column" : "row", gap: spacing.sm, justifyContent: "flex-end" }}>
        <Button label="Discard" variant="ghost" onPress={onCancel} fullWidth={compact} />
        <Button label="Check with Smart Send" variant="secondary" onPress={check} loading={busy === "check"} fullWidth={compact} />
        {blocked ? (
          <Button label="Send anyway" variant="danger" onPress={() => send(true)} loading={busy === "send"} fullWidth={compact} />
        ) : (
          <Button label="Send" onPress={() => send(false)} loading={busy === "send"} fullWidth={compact} />
        )}
      </View>
    </ScrollView>
  );
}
