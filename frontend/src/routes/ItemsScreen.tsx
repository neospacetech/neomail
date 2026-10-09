import { useApiClient } from "@neospacetech/neosuite-runtime/react";
import { spacing } from "@neospacetech/neosuite-tokens";
import {
  AdaptiveLayout,
  Button,
  DataView,
  ListDetail,
  Row,
  Stack,
  Text,
  TextField,
  useBreakpoint,
  type DataColumn,
} from "@neospacetech/neosuite-ui";
import { useCallback, useState } from "react";
import { ScrollView, View } from "react-native";
import { errorMessage, transitionItem, validateItem } from "../api";
import type { Item } from "../types";
import { ItemStatusBadge } from "../widgets/ItemStatusBadge";

const STATUS_LABEL = { todo: "To do", doing: "In progress", done: "Done" } as const;

const columns: DataColumn<Item>[] = [
  { key: "title", header: "Title", value: (item) => item.title, primary: true, flex: 3 },
  { key: "status", header: "Status", render: (item) => <ItemStatusBadge status={item.status} />, flex: 1 },
  { key: "slug", header: "Slug", value: (item) => item.slug, flex: 2 },
];

/**
 * Item list with a create form and a detail pane.
 *
 * Layout by breakpoint: on compact the form stacks above a card list and the detail takes over the
 * list (with a back button); from medium up the form is one row and list and detail sit side by
 * side as a table plus pane. All state lives here, so resizing never loses input or selection.
 */
export function ItemsScreen() {
  const client = useApiClient();
  const { breakpoint } = useBreakpoint();
  const compact = breakpoint === "compact";

  const [items, setItems] = useState<Item[]>([]);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [draftError, setDraftError] = useState<string | undefined>();
  const [creating, setCreating] = useState(false);

  const create = useCallback(async () => {
    setCreating(true);
    try {
      const item = await validateItem(client, draft);
      setItems((current) => (current.some((i) => i.slug === item.slug) ? current : [...current, item]));
      setDraft("");
      setDraftError(undefined);
    } catch (error) {
      setDraftError(errorMessage(error));
    } finally {
      setCreating(false);
    }
  }, [client, draft]);

  const replace = useCallback((next: Item) => {
    setItems((current) => current.map((item) => (item.slug === next.slug ? next : item)));
  }, []);

  return (
    <Stack flex>
      <View
        style={{
          flexDirection: compact ? "column" : "row",
          alignItems: compact ? "stretch" : "flex-end",
          gap: spacing.sm,
          padding: compact ? spacing.md : spacing.lg,
        }}
      >
        <TextField
          label="New item"
          value={draft}
          onChangeText={setDraft}
          onSubmitEditing={create}
          error={draftError}
          helperText="Up to 200 characters."
          returnKeyType="done"
          style={compact ? undefined : { flex: 1 }}
        />
        <Button label="Add item" onPress={create} loading={creating} fullWidth={compact} />
      </View>
      <ListDetail
        selectedId={selectedSlug}
        onSelectionChange={setSelectedSlug}
        backLabel="All items"
        renderList={({ select }) => (
          <DataView
            data={items}
            columns={columns}
            keyExtractor={(item) => item.slug}
            onRowPress={(item) => select(item.slug)}
            accessibilityLabel="Items"
            emptyState={
              <Text tone="muted" style={{ padding: spacing.lg }}>
                No items yet. Add one above.
              </Text>
            }
          />
        )}
        renderDetail={({ selectedId }) => {
          const item = items.find((i) => i.slug === selectedId);
          return item ? <ItemDetail item={item} onChange={replace} /> : <Text tone="muted">Item not found.</Text>;
        }}
        emptyDetail={
          <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.lg }}>
            <Text tone="muted">Select an item to see its details.</Text>
          </View>
        }
      />
    </Stack>
  );
}

function ItemDetail({ item, onChange }: { item: Item; onChange: (item: Item) => void }) {
  const client = useApiClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const advance = useCallback(async () => {
    setBusy(true);
    setError(undefined);
    try {
      const result = await transitionItem(client, item);
      onChange({ ...item, status: result.status, next_status: result.next_status });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }, [client, item, onChange]);

  const next = item.next_status;
  const action = next ? (
    <Button label={`Move to ${STATUS_LABEL[next]}`} onPress={advance} loading={busy} />
  ) : (
    <Text tone="muted">This item is finished.</Text>
  );
  const facts = (
    <Stack gap="xs">
      <Text variant="label" tone="muted">
        Slug
      </Text>
      <Text variant="code" selectable>
        {item.slug}
      </Text>
    </Stack>
  );

  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.lg }}>
      <Stack gap="sm">
        <Text variant="title" headingLevel={1}>
          {item.title}
        </Text>
        <ItemStatusBadge status={item.status} />
      </Stack>
      <AdaptiveLayout
        compact={
          <Stack gap="lg">
            {facts}
            {action}
          </Stack>
        }
        expanded={
          <Row gap="xl" justify="space-between" wrap>
            {facts}
            {action}
          </Row>
        }
      />
      {error ? (
        <Text tone="danger" role="alert">
          {error}
        </Text>
      ) : null}
    </ScrollView>
  );
}
