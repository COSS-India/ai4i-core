import { useState, useEffect, useCallback } from "react";
import {
  getServiceById,
  updateService,
  type Service,
} from "../../services/servicesManagementService";
import { getModelById } from "../../services/modelManagementService";
import { extractErrorInfo } from "../../utils/errorHandler";
import { useToastWithDeduplication } from "../useToastWithDeduplication";
import { invalidateServiceRegistryQueries } from "../../components/services-management/utils";
import type { FetchServicesRef, HandleViewServiceRef, RegistryPageContext } from "./shared";

type UseServiceDetailParams = RegistryPageContext & {
  fetchServicesRef: FetchServicesRef;
  handleViewServiceRef: HandleViewServiceRef;
  setActiveTab: React.Dispatch<React.SetStateAction<number>>;
};

export function useServiceDetail({
  router,
  queryClient,
  viewTabIndex,
  checkSessionExpiry,
  fetchServicesRef,
  handleViewServiceRef,
  setActiveTab,
}: UseServiceDetailParams) {
  const toast = useToastWithDeduplication();
  const [selectedService, setSelectedService] = useState<Service | null>(null);
  const [isViewingService, setIsViewingService] = useState(false);
  const [isEditingService, setIsEditingService] = useState(false);
  const [updateFormData, setUpdateFormData] = useState<Partial<Service>>({});
  const [isUpdating, setIsUpdating] = useState(false);
  const [selectedServiceModelDeprecated, setSelectedServiceModelDeprecated] = useState<
    boolean | null
  >(null);

  const handleViewService = useCallback(
    async (serviceId: string) => {
      if (!checkSessionExpiry()) return;
      setSelectedServiceModelDeprecated(null);
      try {
        const service = await getServiceById(serviceId);
        setSelectedService(service);
        setUpdateFormData(service);
        setIsViewingService(true);
        setActiveTab(viewTabIndex);
        router.replace(
          { pathname: "/services-management", query: { ...router.query, tab: "2" } },
          undefined,
          { shallow: true }
        );
        const modelId = service.modelId || service.model_id;
        if (modelId) {
          try {
            const modelDetails = await getModelById(modelId);
            const deprecated =
              modelDetails?.versionStatus &&
              typeof modelDetails.versionStatus === "string" &&
              modelDetails.versionStatus.toLowerCase() === "deprecated";
            setSelectedServiceModelDeprecated(!!deprecated);
          } catch {
            setSelectedServiceModelDeprecated(false);
          }
        } else {
          setSelectedServiceModelDeprecated(false);
        }
      } catch (error: unknown) {
        const { title: errorTitle, message: errorMsg, showOnlyMessage } = extractErrorInfo(error);
        toast({
          title: showOnlyMessage ? undefined : errorTitle,
          description: errorMsg,
          status: "error",
          duration: 5000,
          isClosable: true,
        });
      }
    },
    [checkSessionExpiry, router, setActiveTab, toast, viewTabIndex]
  );

  useEffect(() => {
    handleViewServiceRef.current = handleViewService;
  }, [handleViewService, handleViewServiceRef]);

  const handleUpdateService = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!checkSessionExpiry()) return;

    if (!selectedService?.serviceId) {
      toast({
        title: "Update Failed",
        description: "Service ID is required for update",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      return;
    }

    setIsUpdating(true);

    try {
      const updatedService = await updateService({
        ...updateFormData,
        serviceId: selectedService.serviceId,
      });

      invalidateServiceRegistryQueries(queryClient);

      toast({
        title: "Service Updated",
        description: "Service has been updated successfully",
        status: "success",
        duration: 3000,
        isClosable: true,
      });

      setSelectedService(updatedService);
      setIsEditingService(false);

      await fetchServicesRef.current?.();
    } catch (error: unknown) {
      const { title: errorTitle, message: errorMsg, showOnlyMessage } = extractErrorInfo(error);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMsg,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsUpdating(false);
    }
  };

  return {
    selectedService,
    setSelectedService,
    isViewingService,
    setIsViewingService,
    isEditingService,
    updateFormData,
    isUpdating,
    selectedServiceModelDeprecated,
    setSelectedServiceModelDeprecated,
    handleViewService,
    handleUpdateService,
  };
}
