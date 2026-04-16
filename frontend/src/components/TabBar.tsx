import type { Component } from "solid-js";

interface Props {
  sheets: string[];
  activeSheet: string;
  onSelect: (sheet: string) => void;
}

const TabBar: Component<Props> = (props) => {
  return (
    <div class="flex items-center border-b bg-white dark:bg-gray-800 px-2 space-x-1 overflow-x-auto">
      {props.sheets.map((sheet) => (
        <button
          class="px-3 py-1.5 text-sm rounded-t transition-colors-fast whitespace-nowrap"
          classList={{
            "bg-blue-50 text-blue-700 border-t border-x border-blue-200 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-700":
              props.activeSheet === sheet,
            "text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700":
              props.activeSheet !== sheet,
          }}
          onClick={() => props.onSelect(sheet)}
        >
          {sheet}
        </button>
      ))}
    </div>
  );
};

export default TabBar;
