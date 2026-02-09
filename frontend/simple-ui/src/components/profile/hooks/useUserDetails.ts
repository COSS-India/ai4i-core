import { useState, useEffect } from "react";
import { useToast } from "@chakra-ui/react";
import type { User, UserUpdateRequest } from "../../../types/auth";

export interface UseUserDetailsOptions {
  user: User | null;
  updateUser: (data: Partial<User>) => Promise<User>;
  checkSessionExpiry: () => boolean;
}

export function useUserDetails({ user, updateUser, checkSessionExpiry }: UseUserDetailsOptions) {
  const toast = useToast();
  const [isEditingUser, setIsEditingUser] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [userFormData, setUserFormData] = useState<UserUpdateRequest>({
    full_name: "",
    phone_number: "",
    timezone: "UTC",
    language: "en",
    preferences: {},
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (user) {
      setUserFormData({
        full_name: user.full_name || "",
        phone_number: user.phone_number || "",
        timezone: user.timezone || "UTC",
        language: user.language || "en",
        preferences: user.preferences || {},
      });
    }
  }, [user]);

  const validatePhoneNumber = (phoneNumber: string): string | null => {
    if (!phoneNumber || phoneNumber.trim().length === 0) return null;
    const cleanedPhone = phoneNumber.trim().replace(/\s+/g, "").replace(/[-\s()]/g, "");
    let digits = "";
    if (cleanedPhone.startsWith("+91")) {
      digits = cleanedPhone.substring(3);
      if (digits.length === 10 && /^[6-9]\d{9}$/.test(digits)) return null;
    } else if (cleanedPhone.startsWith("91") && cleanedPhone.length === 12) {
      digits = cleanedPhone.substring(2);
      if (/^[6-9]\d{9}$/.test(digits)) return null;
    } else if (cleanedPhone.startsWith("0") && cleanedPhone.length === 11) {
      digits = cleanedPhone.substring(1);
      if (/^[6-9]\d{9}$/.test(digits)) return null;
    } else if (cleanedPhone.length === 10) {
      digits = cleanedPhone;
      if (/^[6-9]\d{9}$/.test(digits)) return null;
    }
    if (cleanedPhone.length > 3) {
      return "Invalid Indian phone number. Please enter a valid 10-digit mobile number (starting with 6-9) or use formats: +91XXXXXXXXXX, 91XXXXXXXXXX, 0XXXXXXXXXX, or XXXXXXXXXX";
    }
    return null;
  };

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};
    if (userFormData.phone_number && userFormData.phone_number.length > 0) {
      const cleanedPhone = userFormData.phone_number.trim().replace(/\s+/g, "").replace(/[-\s()]/g, "");
      let isValid = false;
      let digits = "";
      if (cleanedPhone.startsWith("+91")) {
        digits = cleanedPhone.substring(3);
        isValid = digits.length === 10 && /^[6-9]\d{9}$/.test(digits);
      } else if (cleanedPhone.startsWith("91") && cleanedPhone.length === 12) {
        digits = cleanedPhone.substring(2);
        isValid = /^[6-9]\d{9}$/.test(digits);
      } else if (cleanedPhone.startsWith("0") && cleanedPhone.length === 11) {
        digits = cleanedPhone.substring(1);
        isValid = /^[6-9]\d{9}$/.test(digits);
      } else if (cleanedPhone.length === 10) {
        digits = cleanedPhone;
        isValid = /^[6-9]\d{9}$/.test(digits);
      }
      if (!isValid) {
        newErrors.phone_number =
          "Invalid Indian phone number. Please enter a valid 10-digit mobile number (starting with 6-9) or use formats: +91XXXXXXXXXX, 91XXXXXXXXXX, 0XXXXXXXXXX, or XXXXXXXXXX";
      }
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleEditUser = () => {
    if (!checkSessionExpiry()) return;
    setIsEditingUser(true);
    setErrors({});
  };

  const handleCancelEdit = () => {
    setIsEditingUser(false);
    setErrors({});
    if (user) {
      setUserFormData({
        full_name: user.full_name || "",
        phone_number: user.phone_number || "",
        timezone: user.timezone || "UTC",
        language: user.language || "en",
        preferences: user.preferences || {},
      });
    }
  };

  const handleSaveUser = async () => {
    if (!checkSessionExpiry()) return;
    if (!validateForm()) return;
    setIsSaving(true);
    try {
      const updateData: UserUpdateRequest = {
        full_name: userFormData.full_name?.trim() || "",
        phone_number: userFormData.phone_number?.trim() || "",
        timezone: userFormData.timezone || "UTC",
        language: userFormData.language || "en",
        preferences: userFormData.preferences || {},
      };
      await updateUser(updateData as Partial<User>);
      toast({
        title: "Profile Updated",
        description: "Your profile has been updated successfully",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      setIsEditingUser(false);
      setErrors({});
    } catch (error) {
      toast({
        title: "Update Failed",
        description: error instanceof Error ? error.message : "Failed to update profile",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleInputChange = (field: keyof UserUpdateRequest, value: string | Record<string, unknown>) => {
    setUserFormData((prev) => ({ ...prev, [field]: value }));
    if (field === "phone_number" && typeof value === "string") {
      const error = validatePhoneNumber(value);
      setErrors((prev) => {
        const next = { ...prev };
        if (error) next.phone_number = error;
        else delete next.phone_number;
        return next;
      });
    } else if (errors[field]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  };

  return {
    userFormData,
    isEditingUser,
    isSaving,
    errors,
    handleEditUser,
    handleCancelEdit,
    handleSaveUser,
    handleInputChange,
  };
}
