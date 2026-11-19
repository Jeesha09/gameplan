<template>
  <!-- The panel's scrolling region. In the dialog that is frappe-ui's SettingsBody,
       which brings its own ScrollArea and wide insets. A phone renders the panel as
       a page inside MobileShell, which already scrolls natively, so the body is a
       plain page container — no nested scroller, no dialog insets to undo. -->
  <ScrollArea v-if="asPage" class="min-h-0 flex-1" viewport-class="pb-16">
    <div class="body-container">
      <slot />
    </div>
  </ScrollArea>
  <SettingsBody v-else-if="!isPhone">
    <slot />
  </SettingsBody>
  <!-- pb-16 is SettingsBody's own bottom padding, kept so a panel ends the same
       way in either shell. -->
  <div v-else class="body-container pb-16">
    <slot />
  </div>
</template>

<script setup lang="ts">
import { inject } from 'vue'
import { ScrollArea, SettingsBody } from 'frappe-ui'
import { useIsMobile } from '@/utils/useIsMobile'
import { panelAsPage } from './index'

const isPhone = useIsMobile()
const asPage = inject(panelAsPage, false)
</script>
