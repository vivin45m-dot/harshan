import { createContext, useContext } from 'react'

export const ThemeContext = createContext('system')
export const useThemeName = () => useContext(ThemeContext)
