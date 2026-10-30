import { toast } from "./toast.svelte";

export async function copy(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (e) {
    toast(String(e), "error");
    return false;
  }
}
