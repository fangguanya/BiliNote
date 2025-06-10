import * as React from "react"
import { cn } from "@/lib/utils"

interface CollapsibleProps {
  children: React.ReactNode
  className?: string
}

interface CollapsibleContextValue {
  isOpen: boolean
  toggleOpen: () => void
}

const CollapsibleContext = React.createContext<CollapsibleContextValue | null>(null)

const Collapsible: React.FC<CollapsibleProps> = ({ children, className }) => {
  const [isOpen, setIsOpen] = React.useState(false)
  
  const toggleOpen = React.useCallback(() => {
    setIsOpen(prev => !prev)
  }, [])

  const value = React.useMemo(() => ({
    isOpen,
    toggleOpen
  }), [isOpen, toggleOpen])

  return (
    <CollapsibleContext.Provider value={value}>
      <div className={cn("", className)}>
        {children}
      </div>
    </CollapsibleContext.Provider>
  )
}

interface CollapsibleTriggerProps {
  children: React.ReactNode
  className?: string
}

const CollapsibleTrigger: React.FC<CollapsibleTriggerProps> = ({ 
  children, 
  className 
}) => {
  const context = React.useContext(CollapsibleContext)
  
  if (!context) {
    throw new Error('CollapsibleTrigger must be used within a Collapsible')
  }

  const { toggleOpen } = context

  return (
    <button
      type="button"
      onClick={toggleOpen}
      className={cn("w-full text-left", className)}
    >
      {children}
    </button>
  )
}

interface CollapsibleContentProps {
  children: React.ReactNode
  className?: string
}

const CollapsibleContent: React.FC<CollapsibleContentProps> = ({ 
  children, 
  className 
}) => {
  const context = React.useContext(CollapsibleContext)
  
  if (!context) {
    throw new Error('CollapsibleContent must be used within a Collapsible')
  }

  const { isOpen } = context

  return (
    <div
      className={cn(
        "overflow-hidden transition-all duration-200",
        isOpen ? "max-h-screen opacity-100" : "max-h-0 opacity-0",
        className
      )}
    >
      <div className={isOpen ? "pb-2" : ""}>
        {children}
      </div>
    </div>
  )
}

export { Collapsible, CollapsibleTrigger, CollapsibleContent } 