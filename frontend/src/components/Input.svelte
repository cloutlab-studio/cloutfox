<script lang="ts">
  import Icon from "./Icon.svelte";

  let {
    value = $bindable(""),
    placeholder = "",
    type = "text",
    mono = false,
    disabled = false,
    invalid = false,
    autofocus = false,
    reveal = false,
    el = $bindable(),
    onenter,
    oninput,
  }: {
    value?: string;
    placeholder?: string;
    type?: "text" | "password" | "number";
    mono?: boolean;
    disabled?: boolean;
    invalid?: boolean;
    autofocus?: boolean;
    reveal?: boolean;
    el?: HTMLInputElement;
    onenter?: () => void;
    oninput?: (value: string) => void;
  } = $props();

  let shown = $state(false);

  $effect(() => {
    if (autofocus && el) queueMicrotask(() => el?.focus());
  });
</script>

<div class="wrap" class:invalid class:disabled>
  <input
    bind:this={el}
    bind:value
    type={type === "password" && shown ? "text" : type}
    {placeholder}
    {disabled}
    class:mono
    spellcheck="false"
    autocomplete="off"
    onkeydown={(e) => {
      if (e.key === "Enter" && onenter) {
        e.preventDefault();
        onenter();
      }
    }}
    oninput={() => oninput?.(value)}
  />
  {#if reveal && type === "password"}
    <button type="button" class="eye" tabindex="-1" onclick={() => (shown = !shown)} aria-label="show">
      <Icon name="eye" size={16} />
    </button>
  {/if}
</div>

<style>
  .wrap {
    position: relative;
    display: flex;
    min-width: 0;
    border: 2px solid var(--t-line);
    background: var(--t-surface);
    transition:
      box-shadow var(--t-dur) var(--t-ease),
      transform var(--t-dur) var(--t-ease);
  }
  .wrap:focus-within {
    box-shadow: 4px 4px 0 var(--t-focus);
    transform: translate(-1px, -1px);
  }
  .wrap.invalid {
    border-color: var(--error);
    box-shadow: 4px 4px 0 var(--error);
  }
  .wrap.disabled {
    background: var(--t-bg-2);
    border-color: var(--rule-soft);
  }
  input {
    flex: 1;
    min-width: 0;
    height: 38px;
    padding: 0 12px;
    border: 0;
    outline: none;
    background: transparent;
    font-size: 14px;
    user-select: text;
  }
  input::placeholder {
    color: #a39d8a;
  }
  .mono {
    font-family: var(--font-mono);
    font-size: 13px;
  }
  .eye {
    display: grid;
    place-items: center;
    width: 38px;
    border: 0;
    border-left: 2px solid var(--t-line);
    background: var(--t-bg);
    font-size: 14px;
  }
</style>
