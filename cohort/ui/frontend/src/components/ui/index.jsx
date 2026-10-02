import { forwardRef, useId } from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import * as Label from '@radix-ui/react-label'
import * as TabsPrimitive from '@radix-ui/react-tabs'
import * as PopoverPrimitive from '@radix-ui/react-popover'
import * as ToggleGroup from '@radix-ui/react-toggle-group'

export const Button = forwardRef(function Button({ className = 'btn', type = 'button', ...props }, ref) {
  return <button ref={ref} className={className} type={type} {...props} />
})

export function Field({ label, error, children, ...inputProps }) {
  const generated = useId()
  const id = inputProps.id || generated
  return <div className="ui-field">
    <Label.Root htmlFor={id}>{label}</Label.Root>
    {children || <input {...inputProps} id={id} aria-invalid={!!error} aria-describedby={error ? `${id}-error` : undefined} />}
    {error && <p className="error" id={`${id}-error`}>{error}</p>}
  </div>
}

export function Notice({ children, kind = 'error', ...props }) {
  return <p className={kind} role={kind === 'error' ? 'alert' : 'status'} {...props}>{children}</p>
}

export function Dialog({ open, onOpenChange, title, description, children, closeLabel, triggerRef }) {
  return <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="ui-dialog-overlay" />
      <DialogPrimitive.Content className="ui-dialog" onCloseAutoFocus={event => {
        if (triggerRef?.current) { event.preventDefault(); triggerRef.current.focus() }
      }}>
        <div className="ui-dialog-heading">
          <DialogPrimitive.Title>{title}</DialogPrimitive.Title>
          <DialogPrimitive.Close asChild><Button className="btn tiny">{closeLabel}</Button></DialogPrimitive.Close>
        </div>
        <DialogPrimitive.Description className="hint">{description}</DialogPrimitive.Description>
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  </DialogPrimitive.Root>
}

export const TabsRoot = TabsPrimitive.Root
export const TabPanel = TabsPrimitive.Content

export function TabNavigation({ value, items, label, listRef, thumbProps }) {
  return <TabsPrimitive.List aria-label={label} className="tabs" data-view={value} ref={listRef}>
    <span {...thumbProps} />
    {items.map(([key, text]) => <TabsPrimitive.Trigger key={key} className={`tab ${value === key ? 'on' : ''}`} data-view={key} data-seg-on={value === key} value={key}>{text}</TabsPrimitive.Trigger>)}
  </TabsPrimitive.List>
}

export function Badge({ className = 'badge', children, ...props }) {
  return <span className={className} {...props}>{children}</span>
}

export function Popover({ open, onOpenChange, trigger, label, className = '', children }) {
  return <PopoverPrimitive.Root open={open} onOpenChange={onOpenChange}>
    <PopoverPrimitive.Trigger asChild>{trigger}</PopoverPrimitive.Trigger>
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content className={`ui-popover ${className}`} align="end" sideOffset={8} collisionPadding={12} aria-label={label}>
        {children}
      </PopoverPrimitive.Content>
    </PopoverPrimitive.Portal>
  </PopoverPrimitive.Root>
}

export function SegmentedControl({ value, onValueChange, items, label }) {
  return <ToggleGroup.Root type="single" className="seg" value={value} onValueChange={next => { if (next) onValueChange(next) }} aria-label={label}>
    {items.map(([key, text]) => <ToggleGroup.Item key={key} value={key} className={`seg-item ${value === key ? 'on' : ''}`} data-seg-on={value === key}>{text}</ToggleGroup.Item>)}
  </ToggleGroup.Root>
}
