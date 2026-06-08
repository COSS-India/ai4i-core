import type React from "react";
import type { NextRouter } from "next/router";
import type { QueryClient } from "@tanstack/react-query";
import type { Service } from "../../services/servicesManagementService";
import type { ModelDetails } from "../../types/platform";

export type RegistryPageContext = {
  router: NextRouter;
  queryClient: QueryClient;
  isRegistryReadOnly: boolean;
  viewTabIndex: number;
  checkSessionExpiry: () => boolean;
};

export type FetchServicesRef = React.MutableRefObject<(() => Promise<void>) | null>;
export type HandleViewServiceRef = React.MutableRefObject<
  ((serviceId: string) => Promise<void>) | null
>;

export type SelectedServiceSync = {
  selectedService: Service | null;
  setSelectedService: React.Dispatch<React.SetStateAction<Service | null>>;
  setIsViewingService: React.Dispatch<React.SetStateAction<boolean>>;
  setSelectedServiceModelDeprecated: React.Dispatch<React.SetStateAction<boolean | null>>;
  setActiveTab: React.Dispatch<React.SetStateAction<number>>;
};

export const initialCreateFormState = (): Partial<Service> => ({
  name: "",
  serviceDescription: "",
  publishedOn: Math.floor(Date.now() / 1000),
  modelId: "",
  modelName: "",
  endpoint: "",
  task_type: "",
  modelSubmissionDate: "",
  modelVersion: "1.0",
});

export type PreselectedModelState = {
  preselectedModelFromQuery: ModelDetails | null;
  setPreselectedModelFromQuery: React.Dispatch<React.SetStateAction<ModelDetails | null>>;
};
