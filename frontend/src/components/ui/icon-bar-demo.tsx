"use client";

import { Building2, Cloud, GraduationCap, Sun } from "lucide-react";
import { IconBar, IconBarItem } from "@/components/ui/icon-bar";

export function IconBarPreview() {
  return (
    <IconBar>
      <IconBarItem icon={Building2} label="Office" />
      <IconBarItem icon={GraduationCap} label="School" />
      <IconBarItem icon={Sun} label="Sunny" />
      <IconBarItem icon={Cloud} label="Cloudy" />
    </IconBar>
  );
}

export default IconBarPreview;
