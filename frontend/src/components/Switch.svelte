<script lang="ts">
  import { play } from "../lib/sound";

  let {
    checked = $bindable(false),
    label,
    disabled = false,
    onchange,
  }: { checked?: boolean; label?: string; disabled?: boolean; onchange?: (v: boolean) => void } =
    $props();
</script>

<label class="switch" class:disabled>
  <input
    type="checkbox"
    bind:checked
    {disabled}
    onchange={() => {
      play("toggle");
      onchange?.(checked);
    }}
  />
  <span class="track" data-press><span class="knob"></span></span>
  {#if label}<span class="text">{label}</span>{/if}
</label>

<style>
  .switch {
    display: inline-flex;
    align-items: center;
    gap: 12px;
  }
  input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }
  .track {
    position: relative;
    flex: none;
    width: 52px;
    height: 28px;
    border: 2px solid var(--t-line);
    background: var(--t-bg-2);
    transition: background-color var(--t-dur-fast) linear;
  }
  .knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 20px;
    height: 20px;
    background: var(--t-fg);
    transition: transform var(--t-dur) var(--t-ease);
  }
  input:checked + .track {
    background: var(--t-accent);
  }
  input:checked + .track .knob {
    transform: translateX(24px) rotate(90deg);
  }
  input:focus-visible + .track {
    outline: 3px solid var(--t-focus);
    outline-offset: 2px;
  }
  .text {
    font-size: 14px;
  }
  .disabled {
    opacity: 0.5;
  }
</style>
