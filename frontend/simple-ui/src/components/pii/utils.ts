export function actionBadgeColorScheme(action: string): string {
  switch (action) {
    case "MASK":
      return "gray";
    case "HASH":
      return "red";
    default:
      return "blue";
  }
}
