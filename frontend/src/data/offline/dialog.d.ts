// resources.ts stands in for frappe-ui at build time and reads `worksOffline` before opening a
// dialog. TypeScript still checks callers against frappe-ui's own types, so declare it there.
import '../../../node_modules/frappe-ui/src/utils/dialog'

declare module '../../../node_modules/frappe-ui/src/utils/dialog' {
  interface ConfirmArgs {
    /** Open even while offline. Without it, the dialog is refused offline. */
    worksOffline?: boolean
  }
  interface PromptArgs {
    /** Open even while offline. Without it, the dialog is refused offline. */
    worksOffline?: boolean
  }
}
