import { radii, spacing } from "@neospacetech/neosuite-tokens";
import { Interactive, Row, Stack, Text, minTargetFor, usePointerKind, useTheme } from "@neospacetech/neosuite-ui";
import { ScrollView } from "react-native";
import { mailboxLabel } from "../format";
import type { Mailbox } from "../types";

export interface MailboxListProps {
  mailboxes: readonly Mailbox[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** `column`: a sidebar list; `row`: wrapping chips above the thread list. */
  layout: "column" | "row";
}

/** The mailboxes with unread counts. A sidebar on wide screens, chips on narrow ones. */
export function MailboxList({ mailboxes, selectedId, onSelect, layout }: MailboxListProps) {
  const { colors } = useTheme();
  const minHeight = minTargetFor(usePointerKind());
  const items = mailboxes.map((mailbox) => {
    const selected = mailbox.id === selectedId;
    const label = mailboxLabel(mailbox);
    return (
      <Interactive
        key={mailbox.id}
        role="button"
        accessibilityLabel={mailbox.unread > 0 ? `${label}, ${mailbox.unread} unread` : label}
        accessibilityState={{ selected }}
        onPress={() => onSelect(mailbox.id)}
        style={({ hovered }) => ({
          minHeight,
          justifyContent: "center",
          paddingHorizontal: spacing.md,
          borderRadius: layout === "row" ? radii.pill : radii.md,
          borderWidth: layout === "row" ? 1 : 0,
          borderColor: colors.border,
          backgroundColor: selected ? colors.surfacePressed : hovered ? colors.surfaceHover : "transparent",
        })}
      >
        <Row gap="sm" justify="space-between">
          <Text variant={selected ? "label" : "body"} numberOfLines={1} style={{ flexShrink: 1 }}>
            {label}
          </Text>
          {mailbox.unread > 0 ? (
            <Text variant="caption" tone="primary">
              {mailbox.unread}
            </Text>
          ) : null}
        </Row>
      </Interactive>
    );
  });
  if (layout === "row") {
    return (
      <Row gap="xs" wrap padding="sm" accessibilityLabel="Mailboxes">
        {items}
      </Row>
    );
  }
  return (
    <ScrollView accessibilityLabel="Mailboxes" contentContainerStyle={{ padding: spacing.sm }}>
      <Stack gap="xxs">{items}</Stack>
    </ScrollView>
  );
}
