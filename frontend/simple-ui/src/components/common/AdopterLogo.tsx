import { Image, type ImageProps } from "@chakra-ui/react";
import {
  DEFAULT_ADOPTER_LOGO_SRC,
  getAdopterLogoSrc,
  getPlatformName,
} from "../../config/runtimeConfig";

type AdopterLogoProps = Omit<ImageProps, "src" | "alt"> & { alt?: string };

/** ConfigMap logo (`ADOPTER_LOGO_URL`); falls back to default SVG on error. */
export default function AdopterLogo({ alt, ...props }: AdopterLogoProps) {
  return (
    <Image
      src={getAdopterLogoSrc()}
      alt={alt ?? `${getPlatformName()} Logo`}
      objectFit="contain"
      onError={(e) => {
        e.currentTarget.src = DEFAULT_ADOPTER_LOGO_SRC;
      }}
      {...props}
    />
  );
}
