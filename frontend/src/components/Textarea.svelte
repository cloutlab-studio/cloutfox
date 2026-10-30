<script lang="ts">
  let {
    value = $bindable(""),
    placeholder = "",
    rows = 4,
    mono = false,
    maxlength,
    invalid = false,
    onblur,
  }: {
    value?: string;
    placeholder?: string;
    rows?: number;
    mono?: boolean;
    maxlength?: number;
    invalid?: boolean;
    onblur?: () => void;
  } = $props();
</script>

<textarea
  bind:value
  {placeholder}
  {rows}
  {maxlength}
  class:mono
  class:invalid
  spellcheck="false"
  {onblur}
></textarea>

<style>
  textarea {
    width: 100%;
    resize: vertical;
    padding: 9px 12px;
    border: 2px solid var(--t-line);
    border-radius: 0;
    outline: none;
    background: var(--t-surface);
    font-size: 14px;
    line-height: 1.45;
    user-select: text;
    transition:
      box-shadow var(--t-dur) var(--t-ease),
      transform var(--t-dur) var(--t-ease);
  }
  textarea:focus {
    box-shadow: 4px 4px 0 var(--t-focus);
    transform: translate(-1px, -1px);
  }
  textarea.invalid {
    border-color: var(--error);
  }
  textarea::placeholder {
    color: #a39d8a;
  }
  .mono {
    font-family: var(--font-mono);
    font-size: 12.5px;
  }
</style>
