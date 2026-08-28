import React, { useMemo, useRef } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Grid, OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { useCampus3D } from '../hooks/useCampus3D';
import { CampoDeCadeiras } from './ChairNode';
import { RoomNode } from './RoomNode';
import { CatracaNode } from './CatracaNode';
import { INSTED } from '../lib/theme';
import type { Cadeira, EventoCatraca, Pavimento } from '../lib/types';

const ALTURA_PAVIMENTO = 4.2;
/** Afastamento extra entre lajes na visao de campus (maquete "explodida"). */
const EXPLOSAO = 5.5;

/* ------------------------------------------------------------------ *
 * Camera com transicao suave entre os modos de visao
 * ------------------------------------------------------------------ */

function CameraDirigida({ alvoY }: { alvoY: number }) {
  const { camera } = useThree();
  const controlsRef = useRef<any>(null);
  const alvo = useRef(new THREE.Vector3(0, alvoY, 0));

  alvo.current.set(0, alvoY, 0);

  useFrame(() => {
    if (!controlsRef.current) return;
    controlsRef.current.target.lerp(alvo.current, 0.07);
    controlsRef.current.update();
  });

  return (
    <OrbitControls
      ref={controlsRef}
      enablePan
      enableDamping
      dampingFactor={0.08}
      minDistance={22}
      maxDistance={260}
      maxPolarAngle={Math.PI / 2.06}
      makeDefault
    />
  );
}

/* ------------------------------------------------------------------ *
 * Um pavimento completo
 * ------------------------------------------------------------------ */

interface CamadaProps {
  pavimento: Pavimento;
  offsetY: number;
  detalhado: boolean;
  atenuado: boolean;
}

const CamadaPavimento: React.FC<CamadaProps> = ({
  pavimento,
  offsetY,
  detalhado,
  atenuado,
}) => {
  const statusCadeiras = useCampus3D((s) => s.statusCadeiras);
  const dashboard = useCampus3D((s) => s.dashboard);
  const salaFoco = useCampus3D((s) => s.salaFoco);
  const salaPiscando = useCampus3D((s) => s.salaPiscando);
  const abrirSala = useCampus3D((s) => s.abrirSala);

  const ocupacaoPorSala = useMemo(() => {
    const mapa: Record<string, any> = {};
    for (const o of dashboard?.ocupacao_salas ?? []) mapa[o.sala_id] = o;
    return mapa;
  }, [dashboard]);

  const cadeiras = useMemo<Cadeira[]>(
    () => pavimento.salas.flatMap((s) => s.cadeiras),
    [pavimento],
  );

  // Laje base: envolve exatamente as salas do pavimento (implantacao em L).
  const laje = useMemo(() => {
    const xs: number[] = [];
    const zs: number[] = [];
    for (const s of pavimento.salas) {
      xs.push(s.posicao.x, s.posicao.x + s.dimensao.largura);
      zs.push(s.posicao.z, s.posicao.z + s.dimensao.profundidade);
    }
    if (!xs.length) return null;
    const margem = 2.5;
    const x0 = Math.min(...xs) - margem;
    const x1 = Math.max(...xs) + margem;
    const z0 = Math.min(...zs) - margem;
    const z1 = Math.max(...zs) + margem;
    return {
      cx: (x0 + x1) / 2,
      cz: (z0 + z1) / 2,
      largura: x1 - x0,
      profundidade: z1 - z0,
    };
  }, [pavimento]);

  return (
    <group>
      {laje && (
        <mesh
          position={[laje.cx, pavimento.altura_y + offsetY - 0.16, laje.cz]}
          receiveShadow
        >
          <boxGeometry args={[laje.largura, 0.22, laje.profundidade]} />
          <meshStandardMaterial
            color="#131a23"
            roughness={0.95}
            transparent
            opacity={atenuado ? 0.3 : 0.72}
          />
        </mesh>
      )}

      {pavimento.salas.map((sala) => (
        <RoomNode
          key={sala.id}
          sala={sala}
          offsetY={offsetY}
          ocupacao={ocupacaoPorSala[sala.id]}
          destacada={salaFoco === sala.id}
          piscandoEm={salaPiscando[sala.id]}
          mostrarRotulo={detalhado}
          onSelecionar={abrirSala}
        />
      ))}

      {cadeiras.length > 0 && (
        <CampoDeCadeiras
          cadeiras={cadeiras}
          statusPorId={statusCadeiras}
          offsetY={offsetY}
          onSelecionarSala={abrirSala}
          atenuado={atenuado}
        />
      )}
    </group>
  );
};

/* ------------------------------------------------------------------ *
 * Cena
 * ------------------------------------------------------------------ */

function Cena() {
  const maquete = useCampus3D((s) => s.maquete);
  const modoVisao = useCampus3D((s) => s.modoVisao);
  const pavimentoSelecionado = useCampus3D((s) => s.pavimentoSelecionado);
  const eventos = useCampus3D((s) => s.eventos);

  // Ultimo pulso por catraca, para animar o torniquete.
  const pulsoPorCatraca = useMemo(() => {
    const mapa: Record<string, number> = {};
    for (const e of eventos.slice(0, 12) as EventoCatraca[]) {
      if (!mapa[e.catraca_id]) mapa[e.catraca_id] = Date.parse(e.timestamp);
    }
    return mapa;
  }, [eventos]);

  if (!maquete) return null;

  const foco = modoVisao === 'PAVIMENTO' ? pavimentoSelecionado : null;
  const pavAtivo = maquete.pavimentos.find((p) => p.id === foco);

  const alvoY =
    modoVisao === 'PAVIMENTO'
      ? 1.5
      : (maquete.pavimentos.length * (ALTURA_PAVIMENTO + EXPLOSAO)) / 2 - 2;

  return (
    <>
      <color attach="background" args={['#0b1016']} />
      <fog attach="fog" args={['#0b1016', 150, 420]} />

      <ambientLight intensity={0.55} />
      <hemisphereLight args={['#4a5b6b', '#0b1016', 0.55]} />
      <directionalLight
        position={[70, 95, 55]}
        intensity={1.15}
        castShadow
        shadow-mapSize={[1024, 1024]}
      />
      <pointLight position={[-45, 26, -34]} color={INSTED.primary} intensity={80} distance={130} />
      <pointLight position={[48, 22, 40]} color="#3B82F6" intensity={60} distance={130} />

      <Grid
        position={[0, -0.5, 0]}
        args={[420, 420]}
        cellSize={5}
        cellThickness={0.5}
        cellColor="#1c2530"
        sectionSize={25}
        sectionThickness={1}
        sectionColor="#243040"
        fadeDistance={340}
        fadeStrength={1.4}
        infiniteGrid
      />

      {modoVisao === 'PAVIMENTO' && pavAtivo ? (
        <CamadaPavimento
          key={pavAtivo.id}
          pavimento={pavAtivo}
          offsetY={-pavAtivo.altura_y}
          detalhado
          atenuado={false}
        />
      ) : (
        maquete.pavimentos.map((pav) => (
          <CamadaPavimento
            key={pav.id}
            pavimento={pav}
            offsetY={pav.ordem * EXPLOSAO}
            detalhado={false}
            atenuado={false}
          />
        ))
      )}

      {maquete.catracas
        .filter(() => modoVisao === 'CAMPUS' || pavimentoSelecionado === 'TERREO')
        .map((c) => (
          <CatracaNode
            key={c.id}
            catraca={c}
            offsetY={modoVisao === 'PAVIMENTO' ? 0 : 0}
            pulsoEm={pulsoPorCatraca[c.id]}
          />
        ))}

      <CameraDirigida alvoY={alvoY} />
    </>
  );
}

export const Canvas3D: React.FC = () => (
  <Canvas
    shadows
    dpr={[1, 1.8]}
    camera={{ position: [82, 66, 96], fov: 42, near: 0.1, far: 900 }}
    gl={{ antialias: true, powerPreference: 'high-performance' }}
  >
    <Cena />
  </Canvas>
);
