// Speech to Speech Icon Component - Uses SVG image icon
import React from "react";
import { Image } from "@chakra-ui/react";
import { IconType } from "react-icons";

// Component that renders the speech-to-speech icon image (two microphones with wave)
const DoubleMicrophoneIcon = React.forwardRef<SVGSVGElement, any>((props, ref) => {
  const { boxSize, color, ...rest } = props;
  // Increase size - multiply by 2.0 to make it 200% larger
  const size = boxSize ? Math.floor(boxSize * 2.0) : 48;
  
  return (
    <Image
      src="/speech-to-speech-icon.svg"
      alt="Speech to Speech"
      boxSize={size}
      objectFit="contain"
      display="inline-block"
      {...rest}
    />
  ) as any;
});

(DoubleMicrophoneIcon as any).displayName = "DoubleMicrophoneIcon";

export default DoubleMicrophoneIcon as IconType;

