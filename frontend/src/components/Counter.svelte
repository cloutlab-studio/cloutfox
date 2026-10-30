<script lang="ts">
  // A number whose digits roll to the new value.
  let { value }: { value: number } = $props();
  const digits = $derived(String(value).split(""));
</script>

<span class="counter" aria-label={String(value)}>
  {#each digits as d, i (digits.length - i)}
    <span class="digit" aria-hidden="true">
      <span class="reel" style:--d={Number(d)}>
        {#each Array(10) as _, n (n)}<span>{n}</span>{/each}
      </span>
    </span>
  {/each}
</span>

<style>
  .counter {
    display: inline-flex;
    font-variant-numeric: tabular-nums;
  }
  .digit {
    display: inline-block;
    height: 1em;
    overflow: hidden;
    line-height: 1;
  }
  .reel {
    display: flex;
    flex-direction: column;
    transform: translateY(calc(var(--d) * -1em));
    transition: transform 0.7s var(--t-ease);
  }
  .reel span {
    height: 1em;
  }
</style>
