import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Home from './pages/Home'
import Wardrobe from './pages/Wardrobe'
import TryOn from './pages/TryOn'

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50">
        <nav className="bg-white shadow-sm border-b border-gray-200">
          <div className="max-w-lg mx-auto px-4 py-3 flex justify-between items-center">
            <h1 className="text-lg font-bold text-gray-900">AI 智能衣橱</h1>
            <div className="flex gap-4">
              <NavLink to="/" className="text-gray-600 hover:text-gray-900">今日推荐</NavLink>
              <NavLink to="/wardrobe" className="text-gray-600 hover:text-gray-900">我的衣柜</NavLink>
              <NavLink to="/tryon" className="text-gray-600 hover:text-gray-900">AI 试穿</NavLink>
            </div>
          </div>
        </nav>
        <main className="max-w-lg mx-auto px-4 py-6">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/wardrobe" element={<Wardrobe />} />
            <Route path="/tryon" element={<TryOn />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App