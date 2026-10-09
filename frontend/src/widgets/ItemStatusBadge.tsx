import { radii, spacing } from "@neospacetech/neosuite-tokens";
import { Text, useTheme } from "@neospacetech/neosuite-ui";
import { View } from "react-native";
import type { ItemStatus } from "../types";

const LABELS: Record<ItemStatus, string> = { todo: "To do", doing: "In progress", done: "Done" };

export interface ItemStatusBadgeProps {
  status: ItemStatus;
}

/** Compact status label. Embeddable anywhere an item is shown, including other products. */
export function ItemStatusBadge({ status }: ItemStatusBadgeProps) {
  const { colors } = useTheme();
  const tone = status === "done" ? "success" : status === "doing" ? "primary" : "muted";
  return (
    <View
      accessibilityLabel={`Status: ${LABELS[status]}`}
      style={{
        alignSelf: "flex-start",
        paddingHorizontal: spacing.sm,
        paddingVertical: spacing.xxs,
        borderRadius: radii.md,
        borderWidth: 1,
        borderColor: colors.border,
      }}
    >
      <Text variant="caption" tone={tone}>
        {LABELS[status]}
      </Text>
    </View>
  );
}
