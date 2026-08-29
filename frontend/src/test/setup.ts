import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

// Testing Library only auto-registers this under vitest `globals: true`, which
// the config deliberately does not set; without it renders stack in one
// document and a second render makes every getBy* find two matches.
afterEach(cleanup)

// jsdom ships <dialog> without its methods, and Sheet calls them directly to
// get the platform's focus trap. Enough of them to let sheets render in tests.
if (typeof HTMLDialogElement !== 'undefined' && !HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true
  }
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.open = false
    this.dispatchEvent(new Event('close'))
  }
}
