<script lang="ts">
  import { close, stack } from "../lib/overlay.svelte";
</script>

{#each stack as entry, i (entry.id)}
  {@const Component = entry.component}
  <div class="layer" style:z-index={100 + i}>
    <button
      type="button"
      class="backdrop"
      class:drawer={entry.props.drawer === true}
      aria-label="close"
      tabindex="-1"
      onclick={() => !entry.props.sticky && close(entry.id)}
    ></button>
    <div class="slot" class:right={entry.props.drawer === true}>
      <Component {...entry.props} close={(value?: unknown) => close(entry.id, value)} />
    </div>
  </div>
{/each}

<style>
  .layer {
    position: fixed;
    inset: 0;
  }
  .backdrop {
    position: absolute;
    inset: 0;
    border: 0;
    padding: 0;
    background:
      repeating-linear-gradient(-45deg, rgb(10 10 10 / 0.08) 0 2px, transparent 2px 9px),
      rgb(245 240 225 / 0.72);
    animation: fade 0.25s linear;
  }
  .backdrop.drawer {
    background:
      repeating-linear-gradient(-45deg, rgb(10 10 10 / 0.06) 0 2px, transparent 2px 9px),
      rgb(245 240 225 / 0.5);
  }
  .slot {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    pointer-events: none;
  }
  .slot > :global(*) {
    pointer-events: auto;
  }
  .slot.right {
    display: block;
  }
  @keyframes fade {
    from {
      opacity: 0;
    }
  }
</style>
