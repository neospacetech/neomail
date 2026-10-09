/**
 * NeoMail client module for the neosuite-app shell.
 *
 * - `routes`: screens mounted under `/neomail`.
 * - `widgets`: embeddable views, keyed by widget id.
 * - `context`: what NeoMind may know and do while a NeoMail screen is open.
 */
export * from "./api";
export { FindingList, MailboxList, ThreadRow, type MailboxListProps, type ThreadRowProps } from "./components";
export { context } from "./context";
export * from "./format";
export type { ContextDescriptor, ContextSnapshot, ProductRoute, WidgetDescriptor } from "./module";
export { Composer, MailScreen, ThreadView, routes, type ComposerInitial, type ComposerProps, type ThreadViewProps } from "./routes";
export type * from "./types";
export { InboxWidget, widgets, type InboxWidgetProps } from "./widgets";

/** Product id and mount point used by the shell. */
export const product = { id: "neomail", title: "NeoMail", basePath: "/neomail" } as const;
