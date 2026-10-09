import { radii, spacing } from "@neospacetech/neosuite-tokens";
import { Stack, Text, useTheme } from "@neospacetech/neosuite-ui";
import { View } from "react-native";
import type { SmartSendFinding } from "../types";

const TITLES: Record<SmartSendFinding["rule"], string> = {
  overlap: "Calendar conflict",
  out_of_office: "Out of office",
  focus_time: "Focus time",
  elsewhere_then: "You'll be elsewhere",
  missing_attachment: "Missing attachment",
  missing_recipient: "Missing recipient",
};

/** Smart Send findings, each with its rule and a one-sentence reason. */
export function FindingList({ findings }: { findings: readonly SmartSendFinding[] }) {
  const { colors } = useTheme();
  if (findings.length === 0) return null;
  return (
    <Stack gap="sm" role="list" aria-live="polite" accessibilityLabel="Smart Send findings">
      {findings.map((finding, index) => {
        const tone = finding.severity === "conflict" ? "danger" : finding.severity === "warn" ? "warning" : "muted";
        return (
          <View
            key={`${finding.claim}-${finding.rule}-${index}`}
            role="listitem"
            style={{
              padding: spacing.md,
              gap: spacing.xxs,
              borderRadius: radii.md,
              borderWidth: 1,
              borderColor: finding.severity === "conflict" ? colors.danger : finding.severity === "warn" ? colors.warning : colors.border,
            }}
          >
            <Text variant="label" tone={tone}>
              {TITLES[finding.rule]}
            </Text>
            <Text>{finding.why}</Text>
          </View>
        );
      })}
    </Stack>
  );
}
