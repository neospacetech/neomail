import type { ProductRoute } from "../module";
import { MailScreen } from "./MailScreen";

export { MailScreen };
export { Composer, type ComposerInitial, type ComposerProps } from "./Composer";
export { ThreadView, type ThreadViewProps } from "./ThreadView";

/** Screens mounted by the shell under `/neomail`. */
export const routes: ProductRoute[] = [{ path: "", title: "Mail", nav: true, component: MailScreen }];
