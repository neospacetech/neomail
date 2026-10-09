import { useApiClient } from "@neospacetech/neosuite-runtime/react";
import { spacing } from "@neospacetech/neosuite-tokens";
import { AdaptiveLayout, Button, Stack, Text, TextField, useBreakpoint } from "@neospacetech/neosuite-ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { FlatList, View } from "react-native";
import { errorMessage, streamLifecycle, type LifecycleEvent } from "../api";

function describe(event: LifecycleEvent): string {
  switch (event.event) {
    case "item.created":
      return `Created "${event.data.title}" (${event.data.status})`;
    case "item.status":
      return `${event.data.previous_status} -> ${event.data.status}`;
    case "end":
      return "Stream finished";
  }
}

/**
 * Streaming example: runs an item through its lifecycle on the server and shows the server-sent
 * events as they arrive. Form and log stack on compact and medium, and sit side by side from
 * expanded up. The stream is cancelled when the screen unmounts or a new run starts.
 */
export function LifecycleScreen() {
  const client = useApiClient();
  const { breakpoint } = useBreakpoint();
  const [title, setTitle] = useState("Write the release notes");
  const [events, setEvents] = useState<LifecycleEvent[]>([]);
  const [error, setError] = useState<string | undefined>();
  const [running, setRunning] = useState(false);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => () => abort.current?.abort(), []);

  const run = useCallback(async () => {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setEvents([]);
    setError(undefined);
    setRunning(true);
    try {
      for await (const event of streamLifecycle(client, title, controller.signal)) {
        setEvents((current) => [...current, event]);
      }
    } catch (e) {
      if (!controller.signal.aborted) setError(errorMessage(e));
    } finally {
      if (abort.current === controller) setRunning(false);
    }
  }, [client, title]);

  const padding = breakpoint === "compact" ? spacing.md : spacing.lg;

  const form = (
    <Stack gap="sm" style={{ padding }}>
      <TextField label="Title" value={title} onChangeText={setTitle} onSubmitEditing={run} error={error} />
      <Button label="Run lifecycle" onPress={run} loading={running} fullWidth={breakpoint === "compact"} />
    </Stack>
  );

  const log = (
    <FlatList
      data={events}
      keyExtractor={(event, index) => event.id ?? String(index)}
      aria-label="Lifecycle events"
      aria-live="polite"
      contentContainerStyle={{ padding, gap: spacing.sm }}
      ListEmptyComponent={<Text tone="muted">Run the lifecycle to see events here.</Text>}
      renderItem={({ item }) => (
        <Stack gap="xxs">
          <Text variant="label">{item.event}</Text>
          <Text>{describe(item)}</Text>
        </Stack>
      )}
    />
  );

  return (
    <AdaptiveLayout
      compact={
        <Stack flex>
          {form}
          {log}
        </Stack>
      }
      expanded={
        <View style={{ flex: 1, flexDirection: "row" }}>
          <View style={{ width: "40%", minWidth: 280 }}>{form}</View>
          <View style={{ flex: 1, minWidth: 0 }}>{log}</View>
        </View>
      }
    />
  );
}
