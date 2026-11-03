import { readonly, ref } from "vue";

export interface ToastState {
  message: string;
  sticky: boolean;
  visible: boolean;
}

const state = ref<ToastState>({ message: "", sticky: false, visible: false });
let toastTimer: ReturnType<typeof setTimeout> | undefined;

function hideToast(): void {
  clearTimeout(toastTimer);
  state.value = { ...state.value, visible: false };
}

function showToast(message: string, options: { sticky?: boolean } = {}): void {
  clearTimeout(toastTimer);
  const sticky = options.sticky === true;
  state.value = { message, sticky, visible: true };
  if (!sticky) toastTimer = setTimeout(hideToast, 2400);
}

export function useToast() {
  return {
    toast: readonly(state),
    showToast,
    hideToast,
  };
}
