import { useState, useEffect } from "react";
import { showToast } from "../../../utils/toast";
import { canEditOwnProfile } from "../../../utils/rbac";
import type { User, UserUpdateRequest } from "../../../types/auth";

const INDIAN_MOBILE_RE = /^[6-9]\d{9}$/;
const INVALID_PHONE_MSG =
  "Invalid Indian phone number. Please enter a valid 10-digit mobile number (starting with 6-9) or use formats: +91XXXXXXXXXX, 91XXXXXXXXXX, 0XXXXXXXXXX, or XXXXXXXXXX";

function cleanPhoneNumber(phoneNumber: string): string {
  return phoneNumber.trim().replaceAll(/\s+/g, "").replaceAll(/[-\s()]/g, "");
}

function extractIndianMobileDigits(cleanedPhone: string): string | null {
  if (cleanedPhone.startsWith("+91")) {
    const digits = cleanedPhone.slice(3);
    return digits.length === 10 && INDIAN_MOBILE_RE.test(digits) ? digits : null;
  }
  if (cleanedPhone.startsWith("91") && cleanedPhone.length === 12) {
    const digits = cleanedPhone.slice(2);
    return INDIAN_MOBILE_RE.test(digits) ? digits : null;
  }
  if (cleanedPhone.startsWith("0") && cleanedPhone.length === 11) {
    const digits = cleanedPhone.slice(1);
    return INDIAN_MOBILE_RE.test(digits) ? digits : null;
  }
  if (cleanedPhone.length === 10 && INDIAN_MOBILE_RE.test(cleanedPhone)) {
    return cleanedPhone;
  }
  return null;
}

function isValidIndianPhone(phoneNumber: string): boolean {
  if (!phoneNumber.trim() || phoneNumber.includes("*")) return true;
  return extractIndianMobileDigits(cleanPhoneNumber(phoneNumber)) !== null;
}

export interface UseUserDetailsOptions {
  user: User | null;
  updateUser: (data: Partial<User>) => Promise<User>;
  checkSessionExpiry: () => boolean;
}

export function useUserDetails({ user, updateUser, checkSessionExpiry }: UseUserDetailsOptions) {
  const [isEditingUser, setIsEditingUser] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [userFormData, setUserFormData] = useState<UserUpdateRequest>({
    full_name: "",
    phone_number: "",
    timezone: "UTC",
    preferences: {},
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (user) {
      setUserFormData({
        full_name: user.full_name || "",
        phone_number: user.phone_number || "",
        timezone: user.timezone || "UTC",
        preferences: user.preferences || {},
      });
    }
  }, [user]);

  const validatePhoneNumber = (phoneNumber: string): string | null => {
    if (!phoneNumber.trim() || phoneNumber.includes("*")) return null;
    const cleaned = cleanPhoneNumber(phoneNumber);
    if (extractIndianMobileDigits(cleaned)) return null;
    return cleaned.length > 3 ? INVALID_PHONE_MSG : null;
  };

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};
    if (userFormData.phone_number && !isValidIndianPhone(userFormData.phone_number)) {
      newErrors.phone_number = INVALID_PHONE_MSG;
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleEditUser = () => {
    if (!canEditOwnProfile(user?.roles)) return;
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
        preferences: user.preferences || {},
      });
    }
  };

  const handleSaveUser = async () => {
    if (!canEditOwnProfile(user?.roles)) return;
    if (!checkSessionExpiry()) return;
    if (!validateForm()) return;
    setIsSaving(true);
    try {
      const updateData: UserUpdateRequest = {
        full_name: userFormData.full_name?.trim() || "",
        phone_number: userFormData.phone_number?.trim() || "",
        timezone: userFormData.timezone || "UTC",
        preferences: userFormData.preferences || {},
      };
      await updateUser(updateData as Partial<User>);
      showToast({
        type: "success",
        message: "Your profile has been updated successfully",
      });
      setIsEditingUser(false);
      setErrors({});
    } catch (error) {
      showToast({
        type: "error",
        message: error instanceof Error ? error.message : "Failed to update profile",
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
