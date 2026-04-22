import { Navbar, Container, Nav } from 'react-bootstrap'
import { NavLink } from 'react-router-dom'
import { Settings } from 'lucide-react'

function TopNav() {
  return (
    <Navbar className="theme-card rounded-0 border-bottom border-1 border-secondary-subtle">
      <Container fluid="xxl" className="d-flex align-items-center">
        <Navbar.Brand className="text-light fw-bold mb-0">Vantage</Navbar.Brand>
        <Nav className="mx-auto nav-pills">
          <Nav.Link as={NavLink} to="/analyse">Analyse</Nav.Link>
          <Nav.Link as={NavLink} to="/documents">Documents</Nav.Link>
        </Nav>
        <div className="d-flex align-items-center gap-3 text-light">
          <Settings size={18} />
        </div>
      </Container>
    </Navbar>
  )
}

export default TopNav
