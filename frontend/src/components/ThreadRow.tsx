import { spacing } from "@neospacetech/neosuite-tokens";
import { Interactive, Row, Text, minTargetFor, usePointerKind, useTheme } from "@neospacetech/neosuite-ui";
import { View } from "react-native";
import { shortDate } from "../format";
import type { ThreadSummary } from "../types";

export interface ThreadRowProps {
  thread: ThreadSummary;
  selected?: boolean;
  onPress?: (thread: ThreadSummary) => void;
}

/** One conversation in a list: participants, subject, snippet, date and unread state. */
export function ThreadRow({ thread, selected = false, onPress }: ThreadRowProps) {
  const { colors } = useTheme();
  const minHeight = minTargetFor(usePointerKind());
  const unread = thread.unread_count > 0;
  const label = [
    unread ? "Unread" : null,
    thread.flagged ? "Flagged" : null,
    thread.participants.join(", "),
    thread.subject || "(no subject)",
    shortDate(thread.last_at),
    thread.message_count > 1 ? `${thread.message_count} messages` : null,
  ]
    .filter(Boolean)
    .join(", ");
  return (
    <Interactive
      role="button"
      accessibilityLabel={label}
      accessibilityState={{ selected }}
      accessibilityHint="Opens the conversation"
      onPress={() => onPress?.(thread)}
      style={({ hovered, pressed }) => ({
        minHeight,
        paddingHorizontal: spacing.lg,
        paddingVertical: spacing.sm,
        gap: spacing.xxs,
        borderBottomWidth: 1,
        borderColor: colors.border,
        backgroundColor: selected ? colors.surfacePressed : pressed ? colors.surfacePressed : hovered ? colors.surfaceHover : "transparent",
      })}
    >
      <Row gap="sm" justify="space-between">
        <Text variant={unread ? "bodyStrong" : "body"} numberOfLines={1} style={{ flex: 1 }}>
          {thread.participants.join(", ")}
          {thread.message_count > 1 ? ` (${thread.message_count})` : ""}
        </Text>
        <Text variant="caption" tone="muted">
          {shortDate(thread.last_at)}
        </Text>
      </Row>
      <Row gap="xs">
        {unread ? <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.primary }} /> : null}
        <Text variant={unread ? "label" : "body"} numberOfLines={1} style={{ flex: 1 }}>
          {thread.subject || "(no subject)"}
        </Text>
        {thread.flagged ? (
          <Text variant="caption" tone="warning">
            Flagged
          </Text>
        ) : null}
      </Row>
      <Text variant="caption" tone="muted" numberOfLines={2}>
        {thread.snippet}
      </Text>
    </Interactive>
  );
}
