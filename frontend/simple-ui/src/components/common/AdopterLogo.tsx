import { Image, type ImageProps } from "@chakra-ui/react";
import { DEFAULT_ADOPTER_LOGO_SRC } from "../../config/branding";
import { getBranding } from "../../config/runtimeConfig";

type AdopterLogoProps = Omit<ImageProps, "src" | "alt"> & { alt?: string };

/** ConfigMap branding logo (`ADOPTER_LOGO_URL`); falls back to default SVG on error. */
export default function AdopterLogo({ alt, ...props }: AdopterLogoProps) {
  const { name, logoSrc } = getBranding();
  return (
    <Image
      src={logoSrc}
      alt={alt ?? `${name} Logo`}
      objectFit="contain"
      onError={(e) => {
        if (e.currentTarget.src.endsWith(DEFAULT_ADOPTER_LOGO_SRC)) return;
        e.currentTarget.src = DEFAULT_ADOPTER_LOGO_SRC;
      }}
      {...props}
    />
  );
}
