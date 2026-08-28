# Especificação de Código e Arquitetura de Software
## Maquete Virtual 3D & Motor de Ocupação - Insted Centro Universitário

---

### 🎨 Paleta de Cores Institucional (Insted)
Ao construir o CSS, temas e materiais 3D (Three.js/Tailwind), utilize rigorosamente as seguintes variáveis de cor:

```css
:root {
  --insted-primary: #00C9B7;       /* Cyan / Verde Água do Logo */
  --insted-primary-hover: #00B4A2; /* Cyan Escuro para Hovers */
  --insted-dark: #0d1117;          /* Grafite / Fundo Principal Dark Mode */
  --insted-dark-card: #161b22;     /* Cards e Painéis */
  --insted-border: #30363d;        /* Bordas Muted */
  --insted-text-light: #e6edf3;    /* Texto Principal */
  --insted-text-muted: #8b949e;    /* Texto Secundário */
  
  /* Status de Ocupação de Cadeira */
  --status-free: #10B981;          /* Verde (Disponível) */
  --status-reserved: #3B82F6;      /* Azul (Alocado pelo ERP) */
  --status-occupied: #00C9B7;      /* Cyan Insted (Presente via Catraca) */
  --status-alert: #EF4444;         /* Vermelho (Sobrelotação/Erro) */
}
```

---

### 📂 Estrutura do Repositório (Monorepo)

```
insted-virtual-campus/
├── apps/
│   ├── web-3d-frontend/           # Aplicação React + Three.js
│   │   ├── src/
│   │   │   ├── components/
│   │   │   │   ├── Canvas3D.tsx   # Renderizador Three.js
│   │   │   │   ├── FloorMap.tsx   # Seletor de Pavimento (Térreo ao Terraço)
│   │   │   │   ├── ChairNode.tsx  # Componente 3D da Carteira
│   │   │   │   └── ControlPanel/  # Dashboard de Gestão
│   │   │   ├── hooks/
│   │   │   │   ├── useSocket.ts   # Conexão em Tempo Real com Catracas
│   │   │   │   └── useCampus3D.ts # Estado das Salas e Carteiras
│   │   │   └── styles/
│   │   │       └── theme.css
│   └── backend-api/               # API FastAPI (Python)
│       ├── app/
│       │   ├── api/
│       │   │   ├── v1/
│       │   │   │   ├── academico.py  # Endpoints de Integração ERP
│       │   │   │   ├── catracas.py   # Webhook/Socket de Acesso
│       │   │   │   └── alocacao.py   # Motor de Alocação Inteligente
│       │   ├── core/
│       │   │   └── config.py
│       │   ├── models/
│       │   │   ├── sala.py
│       │   │   ├── cadeira.py
│       │   │   └── aluno.py
│       │   └── services/
│       │       └── allocation_engine.py
└── docs/
    ├── Plano_de_Projeto_Maquete_Insted.pdf
    └── Apresentacao_Diretoria_Insted.pdf
```

---

### 🐍 Backend Python (FastAPI): Modelos e Motor de Alocação

#### 1. Modelo de Dados Pydantic (`app/models/cadeira.py`)

```python
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class StatusCadeira(str, Enum):
    LIVRE = "LIVRE"
    RESERVADA = "RESERVADA"
    OCUPADA = "OCUPADA"
    ALERT_SOBRELOTACAO = "ALERT_SOBRELOTACAO"

class Posicao3D(BaseModel):
    x: float
    y: float
    z: float

class CadeiraModel(BaseModel):
    id: str = Field(..., description="ID Único: SALA_101_CAD_01")
    sala_id: str = Field(..., description="ID da Sala/Departamento")
    pavimento: str = Field(..., description="TERREO | PAV_1 | PAV_2 | TERRACIO")
    posicao: Posicao3D
    status: StatusCadeira = StatusCadeira.LIVRE
    aluno_ra: Optional[str] = None
    aluno_nome: Optional[str] = None
```

#### 2. Motor de Alocação de Alunos (`app/services/allocation_engine.py`)

```python
from typing import List, Dict
from app.models.cadeira import CadeiraModel, StatusCadeira

class EngineAlocacaoInsted:
    def __init__(self, cadeiras_sala: List[CadeiraModel]):
        self.cadeiras = cadeiras_sala

    def alocar_turma(self, lista_alunos: List[Dict[str, str]]) -> Dict[str, CadeiraModel]:
        """
        Recebe a lista de alunos matriculados no ERP
        e distribui nas carteiras disponíveis da sala.
        """
        cadeiras_livres = [c for c in self.cadeiras if c.status == StatusCadeira.LIVRE]
        
        if len(lista_alunos) > len(cadeiras_livres):
            raise ValueError(f"Capacidade insuficiente! Alunos: {len(lista_alunos)}, Vagas: {len(cadeiras_livres)}")

        alocacoes = {}
        for index, aluno in enumerate(lista_alunos):
            cadeira = cadeiras_livres[index]
            cadeira.status = StatusCadeira.RESERVADA
            cadeira.aluno_ra = aluno["ra"]
            cadeira.aluno_nome = aluno["nome"]
            alocacoes[aluno["ra"]] = cadeira
            
        return alocacoes

    def registrar_entrada_catraca(self, aluno_ra: str) -> Optional[CadeiraModel]:
        """
        Muda o status da cadeira de RESERVADA para OCUPADA (Cyan Insted)
        quando a catraca detecta a passagem do aluno.
        """
        for cadeira in self.cadeiras:
            if cadeira.aluno_ra == aluno_ra:
                cadeira.status = StatusCadeira.OCUPADA
                return cadeira
        return None
```

---

### 🌐 Frontend React 3D (Three.js): Componente de Renderização de Cadeira

#### `ChairNode.tsx`

```tsx
import React, { useRef } from 'react';
import { MeshProps, useFrame } from '@react-three/fiber';
import * as THREE from 'three';

interface ChairProps extends MeshProps {
  id: string;
  status: 'LIVRE' | 'RESERVADA' | 'OCUPADA' | 'ALERT_SOBRELOTACAO';
  onClickChair: (id: string) => void;
}

const COLOR_MAP = {
  LIVRE: '#10B981',             // Verde
  RESERVADA: '#3B82F6',         // Azul
  OCUPADA: '#00C9B7',           // Cyan Insted
  ALERT_SOBRELOTACAO: '#EF4444' // Vermelho
};

export const ChairNode: React.FC<ChairProps> = ({ id, status, onClickChair, position, ...props }) => {
  const meshRef = useRef<THREE.Mesh>(null!);
  
  const chairColor = COLOR_MAP[status] || '#10B981';

  return (
    <group position={position} onClick={() => onClickChair(id)} {...props}>
      {/* Assento da Carteira */}
      <mesh ref={meshRef} position={[0, 0.4, 0]}>
        <boxGeometry args={[0.5, 0.08, 0.5]} />
        <meshStandardMaterial color={chairColor} roughness={0.3} metalness={0.2} />
      </mesh>
      
      {/* Encosto da Carteira */}
      <mesh position={[0, 0.7, -0.22]}>
        <boxGeometry args={[0.5, 0.5, 0.05]} />
        <meshStandardMaterial color={chairColor} />
      </mesh>
      
      {/* Base / Pés Metallicos */}
      <mesh position={[0, 0.2, 0]}>
        <cylinderGeometry args={[0.03, 0.03, 0.4, 8]} />
        <meshStandardMaterial color="#30363d" />
      </mesh>
    </group>
  );
};
```

---

### 📡 WebSocket Handler para Eventos de Catraca em Tempo Real

```python
# app/api/v1/catracas.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

@router.websocket("/ws/catracas")
async def websocket_catracas(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # data Exemplo: {"event": "CATRACA_PASSAGE", "ra": "20260199", "catraca_id": "CATRACA_BLOCO_A"}
            # Atualiza o status e transmite para a maquete 3D
            await manager.broadcast({
                "type": "CADEIRA_UPDATE",
                "aluno_ra": data.get("ra"),
                "status": "OCUPADA"
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

---

### 📝 Resumo de Integração dos 4 Pavimentos Mapeados
1. **Térreo:** Integração com as catracas principais e Racks 4/5/6.
2. **1º Pavimento:** Mapeamento de salas tradicionais e modulares + Rack 2.
3. **2º Pavimento:** Mapeamento das salas com layout circular e CPD Roxo (Racks R1).
4. **3º Pavimento (Terraço):** Mapeamento do setor administrativo, CED, CHED e Rack 3.
