import type { NextRouter } from "next/router";
import type { Model } from "../../components/model-management/types";

export type { Model };

export type ConfirmAction = "deprecate" | "activate";

export type RegistryPageContext = {
  router: NextRouter;
  isRegistryReadOnly: boolean;
  viewTabIndex: number;
  checkSessionExpiry: () => boolean;
};

export type FetchModelsRef = React.MutableRefObject<(() => Promise<void>) | null>;
export type HandleViewModelRef = React.MutableRefObject<
  ((modelId: string) => Promise<void>) | null
>;
export type OpenConfirmDialogRef = React.MutableRefObject<
  ((action: ConfirmAction, model: Model) => void) | null
>;

export const initialFormData = (): Partial<Model> => ({
  name: "",
  description: "",
  modelId: "",
  license: "",
  source: "",
  task: { type: "" },
  domain: [],
  languages: [],
});
