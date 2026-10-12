/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactElement } from "react";
import { Select } from "@plane/blocks/select";
import type { SelectVariant } from "@plane/blocks/select";
import { cn } from "@plane/utils";
// components
import { OptionDot } from "@/components/custom-fields/value-editor";

export type TChoice = { value: string; label: string; color?: string; group?: string };

type TChoiceSelectProps = {
  /** The property name, announced before the value and shown in the tooltip. */
  fieldLabel: string;
  options: TChoice[];
  value: string | null;
  placeholder: string;
  disabled?: boolean;
  /** Picking the selected option again clears it, unless the field cannot be empty. */
  clearable?: boolean;
  showSearch?: boolean;
  /** The sidebar's ghost select by default; the create form uses pills. */
  variant?: SelectVariant;
  /** Shown before the value when no option color is. */
  icon?: ReactElement<{ className?: string }>;
  onChange: (value: string | null) => void;
};

/** A single choice over the referential, styled like the other work item properties. */
export function ChoiceSelect(props: TChoiceSelectProps) {
  const {
    fieldLabel,
    options,
    value,
    placeholder,
    disabled,
    clearable = true,
    showSearch = false,
    variant = "select-ghost-md",
    icon,
    onChange,
  } = props;
  const selected = options.find((option) => option.value === value) ?? null;
  return (
    <Select<TChoice>
      getValues={() => options}
      value={selected}
      onChange={(next) => {
        if (next && next !== value) onChange(next);
        else if (!next && clearable) onChange(null);
      }}
      disabled={disabled}
      placeholder={placeholder}
      showSearch={showSearch}
      getOptionValue={(option) => option.value}
      getOptionLabel={(option) => option.label}
      getOptionGroup={(option) => option.group}
      getOptionIcon={(option) => (option.color ? <OptionDot color={option.color} /> : undefined)}
    >
      <Select.Trigger<TChoice>
        disabled={disabled}
        tooltip={{ heading: fieldLabel }}
        variant={variant}
        prependIcon={(chosen) => (chosen[0]?.color ? <OptionDot color={chosen[0].color} /> : icon)}
        label={(chosen) => chosen[0]?.label ?? placeholder}
      >
        {(chosen) => (
          <span className={cn("min-w-0 grow truncate text-left", { "text-placeholder": !chosen[0] })}>
            {chosen[0]?.label ?? placeholder}
          </span>
        )}
      </Select.Trigger>
    </Select>
  );
}
